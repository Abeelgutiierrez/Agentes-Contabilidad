"""Agente Reclamador: escribe a los proveedores para pedir las facturas que faltan."""
from __future__ import annotations

from datetime import datetime, timedelta

from ..bus import Mensaje, Temas
from ..models import EmailSaliente, EstadoFaltante, FacturaFaltante, Severidad
from .base import Agente

PROMPT_EMAIL = """Redactas correos breves, cordiales y profesionales en español para que
un pequeño negocio pida a un proveedor una factura pendiente. Incluye los datos
fiscales del cliente para que la factura salga correcta. Si es un recordatorio
(intento > 1) sé algo más firme pero educado. Sin firma inventada: firma con el
nombre de la empresa. Devuelve JSON {"asunto": ..., "cuerpo": ...}."""


class AgenteReclamador(Agente):
    nombre = "reclamador"
    rol = "Reclama por email las facturas que el detective marca como faltantes y escala si no responden."
    fases = ("reclamaciones",)

    def suscribir(self) -> None:
        self.escuchar(Temas.FACTURA_FALTANTE, self._on_faltante)

    def _on_faltante(self, msg: Mensaje) -> None:
        self.reclamar(msg.datos["faltante"])

    def ejecutar_fase(self, fase: str) -> None:
        # Reintentos de las reclamaciones sin respuesta
        for f in self.libro.faltantes_abiertas():
            if f.estado == EstadoFaltante.RECLAMADA:
                self.reclamar(f)

    # ------------------------------------------------------------------
    def reclamar(self, f: FacturaFaltante) -> None:
        if f.estado in (EstadoFaltante.RESUELTA, EstadoFaltante.ESCALADA):
            return
        pol = self.ctx.politicas
        ahora = datetime.combine(self.ctx.hoy, datetime.now().time())
        if f.ultima_reclamacion and ahora - f.ultima_reclamacion < timedelta(days=pol.dias_entre_reclamaciones):
            return
        if f.intentos >= pol.max_reclamaciones:
            self._escalar(f, f"Sin respuesta tras {f.intentos} reclamaciones")
            return
        tercero = self.libro.tercero_por_nif(f.proveedor_nif) if f.proveedor_nif else None
        if not tercero or not tercero.email:
            self._escalar(f, "No se conoce el email del proveedor")
            return
        if self.ctx.correo is None:
            self.incidencia("SIN_CORREO", "No hay conector de correo configurado", Severidad.ERROR)
            return
        email = self.redactar(f, tercero.email, tercero.nombre)
        self.ctx.correo.enviar(email)
        self.libro.emails.append(email)
        f.intentos += 1
        f.ultima_reclamacion = ahora
        f.estado = EstadoFaltante.RECLAMADA
        self.log.info("Reclamación %d enviada a %s", f.intentos, tercero.email)
        self.publicar(Temas.RECLAMACION_ENVIADA, faltante=f, email=email)

    def redactar(self, f: FacturaFaltante, para: str, nombre_proveedor: str) -> EmailSaliente:
        lb = self.libro
        intento = f.intentos + 1
        if self.ctx.llm.disponible:
            datos = self.ctx.llm.completar_json(PROMPT_EMAIL, (
                f"Empresa cliente: {lb.nombre_empresa} (NIF {lb.nif_empresa})\n"
                f"Proveedor: {nombre_proveedor}\nMotivo: {f.motivo}\nPeriodo: {f.periodo}\n"
                f"Importe aproximado: {f.importe_estimado or 'desconocido'}\nIntento número: {intento}"
            ))
            if datos and datos.get("asunto") and datos.get("cuerpo"):
                return EmailSaliente(para=para, asunto=datos["asunto"], cuerpo=datos["cuerpo"], referencia=f.id)
        recordatorio = "Recordatorio: " if intento > 1 else ""
        importe = f" por importe aproximado de {f.importe_estimado} €" if f.importe_estimado else ""
        cuerpo = (
            f"Estimado equipo de {nombre_proveedor}:\n\n"
            f"No nos consta haber recibido la factura correspondiente a {f.periodo or 'la operación indicada'}{importe}.\n"
            f"Detalle: {f.motivo}.\n\n"
            f"¿Podrían enviárnosla respondiendo a este correo? Les recordamos nuestros datos fiscales:\n"
            f"  {lb.nombre_empresa} — NIF {lb.nif_empresa}\n\n"
            f"Muchas gracias.\n\nUn saludo,\n{lb.nombre_empresa}"
        )
        return EmailSaliente(
            para=para,
            asunto=f"{recordatorio}Factura pendiente {f.periodo or ''} — {lb.nombre_empresa}".strip(),
            cuerpo=cuerpo,
            referencia=f.id,
        )

    def _escalar(self, f: FacturaFaltante, motivo: str) -> None:
        f.estado = EstadoFaltante.ESCALADA
        self.incidencia("FALTANTE_ESCALADA", f"{f.proveedor_nombre}: {motivo}. {f.motivo}", Severidad.AVISO, f.id)
        self.publicar(Temas.ESCALADO_HUMANO, motivo=motivo, referencia=f.id, faltante=f)
