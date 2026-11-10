"""Agente Emisor VeriFactu: emite facturas de venta y las remite a la AEAT."""
from __future__ import annotations

from datetime import timedelta
from typing import List

from ..bus import Mensaje, Temas
from ..models import Direccion, EstadoFactura, Factura, Severidad, TipoFactura
from ..verifactu.registro import sobre_suministro
from ..verifactu.validaciones import tipo_iva_valido, validar_nif
from .base import Agente

MAX_REGISTROS_POR_ENVIO = 1000


class AgenteEmisor(Agente):
    nombre = "emisor_verifactu"
    rol = "Numera, registra (huella encadenada + QR) y remite a la AEAT cada factura emitida."
    fases = ("envio_aeat",)

    def suscribir(self) -> None:
        self.escuchar(Temas.FACTURA_A_EMITIR, lambda m: self.emitir(m.datos["factura"]))

    def validar(self, f: Factura) -> List[str]:
        errores = []
        if not f.lineas:
            errores.append("La factura no tiene líneas")
        if f.tipo == TipoFactura.F1 and not (f.receptor_nif and validar_nif(f.receptor_nif)):
            errores.append(f"NIF del destinatario no válido: {f.receptor_nif}")
        if not validar_nif(f.emisor_nif):
            errores.append(f"NIF del emisor no válido: {f.emisor_nif}")
        for l in f.lineas:
            if not tipo_iva_valido(l.tipo_iva):
                errores.append(f"Tipo de IVA no válido: {l.tipo_iva}%")
        if f.fecha > self.ctx.hoy:
            errores.append("La fecha de expedición no puede ser futura")
        return errores

    def emitir(self, f: Factura) -> bool:
        lb = self.libro
        f.direccion = Direccion.EMITIDA
        f.emisor_nif, f.emisor_nombre = lb.nif_empresa, lb.nombre_empresa
        f.serie = f.serie or self.ctx.politicas.serie_por_defecto
        errores = self.validar(f)
        if errores:
            self.incidencia("EMISION_RECHAZADA", f"No se emite la factura a {f.receptor_nombre}: " + "; ".join(errores),
                            Severidad.ERROR, f.id)
            return False
        if not f.numero:
            f.numero = lb.siguiente_numero(f.serie)
        f.vencimiento = f.vencimiento or f.fecha + timedelta(days=self.ctx.politicas.dias_vencimiento)
        registro = self.ctx.verifactu.registrar_alta(f)
        f.estado = EstadoFactura.EMITIDA
        lb.anadir_factura(f)
        self.log.info("Emitida %s (%s €) huella %s…", f.num_serie, f.importe_total, registro.huella[:12])
        self.publicar(Temas.FACTURA_EMITIDA, factura=f, registro=registro)
        return True

    def anular(self, f: Factura) -> None:
        self.ctx.verifactu.registrar_anulacion(f)
        f.estado = EstadoFactura.ANULADA

    def ejecutar_fase(self, fase: str) -> None:
        if self.ctx.aeat is None:
            return
        pendientes = self.ctx.verifactu.pendientes_envio()
        for i in range(0, len(pendientes), MAX_REGISTROS_POR_ENVIO):
            lote = pendientes[i:i + MAX_REGISTROS_POR_ENVIO]
            sobre = sobre_suministro(self.libro.nif_empresa, self.libro.nombre_empresa, lote)
            try:
                resp = self.ctx.aeat.enviar_registros(sobre, [r.secuencia for r in lote])
            except Exception as e:
                self.incidencia("AEAT_ERROR", f"Fallo remitiendo a la AEAT: {e}", Severidad.ERROR)
                return
            for s in resp.aceptados:
                self.ctx.verifactu.marcar_envio(s, "aceptado")
            for s, motivo in resp.rechazados.items():
                self.ctx.verifactu.marcar_envio(s, "rechazado")
                self.incidencia("AEAT_RECHAZO", f"Registro {s} rechazado: {motivo}", Severidad.ERROR, str(s))
            self.publicar(Temas.AEAT_ENVIO, aceptados=len(resp.aceptados), rechazados=len(resp.rechazados),
                          csv=resp.csv, registros=[r.num_serie for r in lote])
            self.log.info("AEAT: %d aceptados, %d rechazados (CSV %s)", len(resp.aceptados), len(resp.rechazados), resp.csv)
