"""Agente de Cobros: envía las facturas emitidas y persigue las impagadas."""
from __future__ import annotations

from datetime import timedelta
from ..bus import Mensaje, Temas
from ..models import Direccion, EmailSaliente, EstadoFactura, Factura, Severidad
from .base import Agente


class AgenteCobros(Agente):
    nombre = "cobros"
    rol = "Envía a cada cliente sus facturas (con el QR VeriFactu) y reclama las vencidas."
    fases = ("cobros",)

    def suscribir(self) -> None:
        self.escuchar(Temas.FACTURA_EMITIDA, self._on_emitida)

    def _on_emitida(self, msg: Mensaje) -> None:
        self.enviar_factura(msg.datos["factura"], msg.datos.get("registro"))

    def enviar_factura(self, f: Factura, registro=None) -> None:
        cliente = self.libro.tercero_por_nif(f.receptor_nif)
        if not cliente or not cliente.email:
            self.incidencia("FACTURA_POR_ENVIAR", f"{f.num_serie}: el cliente {f.receptor_nombre} no tiene email",
                            Severidad.AVISO, f.id)
            return
        if self.ctx.correo is None:
            return
        qr = f"\nVerificable en la AEAT: {registro.url_qr}\n" if registro and registro.url_qr else ""
        lineas = "\n".join(f"  - {l.descripcion}: {l.cantidad} x {l.precio_unitario} € (IVA {l.tipo_iva}%)" for l in f.lineas)
        email = EmailSaliente(
            para=cliente.email,
            asunto=f"Factura {f.num_serie} — {self.libro.nombre_empresa}",
            cuerpo=(
                f"Hola {cliente.nombre}:\n\nLe enviamos la factura {f.num_serie} de fecha {f.fecha:%d/%m/%Y}.\n\n"
                f"{lineas}\n\nBase imponible: {f.base_imponible} €\nIVA: {f.cuota_total} €\n"
                f"TOTAL: {f.importe_total} €\nVencimiento: {f.vencimiento:%d/%m/%Y}\n{qr}\n"
                f"Factura verificable en la sede electrónica de la AEAT (VERI*FACTU).\n\n"
                f"Gracias por su confianza.\n{self.libro.nombre_empresa}"
            ),
            referencia=f.id,
        )
        self.ctx.correo.enviar(email)
        self.libro.emails.append(email)
        if f.estado == EstadoFactura.EMITIDA:
            f.estado = EstadoFactura.ENVIADA
        self.publicar(Temas.FACTURA_ENVIADA, factura=f)

    def ejecutar_fase(self, fase: str) -> None:
        hoy = self.ctx.hoy
        for f in self.libro.facturas_de(Direccion.EMITIDA):
            if f.estado == EstadoFactura.EMITIDA:  # emitida pero nunca enviada
                self.enviar_factura(f)
            if f.estado != EstadoFactura.ENVIADA or not f.vencimiento or f.vencimiento >= hoy:
                continue
            ultimo = self.libro.recordatorios_cobro.get(f.id)
            if ultimo and hoy - ultimo < timedelta(days=self.ctx.politicas.dias_entre_recordatorios_cobro):
                continue
            cliente = self.libro.tercero_por_nif(f.receptor_nif)
            if not (cliente and cliente.email and self.ctx.correo):
                continue
            dias = (hoy - f.vencimiento).days
            email = EmailSaliente(
                para=cliente.email,
                asunto=f"Recordatorio de pago: factura {f.num_serie}",
                cuerpo=(f"Hola {cliente.nombre}:\n\nLa factura {f.num_serie} por {f.importe_total} € venció el "
                        f"{f.vencimiento:%d/%m/%Y} ({dias} días). Si ya la han abonado, ignoren este mensaje.\n\n"
                        f"Un saludo,\n{self.libro.nombre_empresa}"),
                referencia=f.id,
            )
            self.ctx.correo.enviar(email)
            self.libro.emails.append(email)
            self.libro.recordatorios_cobro[f.id] = hoy
            self.incidencia("COBRO_VENCIDO", f"{f.num_serie} de {cliente.nombre}: {f.importe_total} € vencida hace {dias} días",
                            Severidad.AVISO, f.id)
