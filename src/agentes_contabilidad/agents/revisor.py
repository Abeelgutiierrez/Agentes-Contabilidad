"""Agente Revisor (auditor): comprueba el trabajo de los demás agentes."""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from ..bus import Mensaje, Temas
from ..models import Direccion, EstadoFactura, Factura, Severidad
from ..verifactu.validaciones import normalizar_nif, tipo_iva_valido, validar_nif
from .base import Agente


class AgenteRevisor(Agente):
    nombre = "revisor"
    rol = "Audita facturas, numeración, cadena VeriFactu y coherencia contable; abre incidencias."
    fases = ("revision",)

    def suscribir(self) -> None:
        self.escuchar(Temas.FACTURA_RECIBIDA, lambda m: self.revisar_recibida(m.datos["factura"]))

    def revisar_recibida(self, f: Factura) -> None:
        ref = f.id
        if not validar_nif(f.emisor_nif):
            self.incidencia("NIF_PROVEEDOR_INVALIDO", f"{f.emisor_nombre}: NIF {f.emisor_nif} no válido", Severidad.ERROR, ref)
        if f.receptor_nif and normalizar_nif(f.receptor_nif) != self.libro.nif_empresa:
            self.incidencia("RECEPTOR_INCORRECTO",
                            f"Factura {f.num_serie} de {f.emisor_nombre} emitida a {f.receptor_nif}, no a {self.libro.nif_empresa}",
                            Severidad.ERROR, ref)
        if not f.receptor_nif and f.tipo.value == "F1":
            self.incidencia("SIN_NIF_RECEPTOR", f"Factura {f.num_serie} de {f.emisor_nombre} sin nuestro NIF: el IVA podría no ser deducible",
                            Severidad.AVISO, ref)
        if f.total_declarado is not None and abs(f.total_declarado - f.importe_total) > Decimal("0.02"):
            self.incidencia("TOTAL_INCOHERENTE",
                            f"Factura {f.num_serie} de {f.emisor_nombre}: total declarado {f.total_declarado} € ≠ calculado {f.importe_total} €",
                            Severidad.ERROR, ref)
        for l in f.lineas:
            if not tipo_iva_valido(l.tipo_iva):
                self.incidencia("IVA_INUSUAL", f"Factura {f.num_serie}: tipo de IVA {l.tipo_iva}% inusual", Severidad.AVISO, ref)
        if f.fecha > self.ctx.hoy:
            self.incidencia("FECHA_FUTURA", f"Factura {f.num_serie} con fecha futura", Severidad.AVISO, ref)

    def ejecutar_fase(self, fase: str) -> None:
        self.revisar_cadena()
        self.revisar_numeracion()
        self.revisar_envios()

    def revisar_cadena(self) -> None:
        for e in self.ctx.verifactu.verificar_cadena():
            self.incidencia("CADENA_VERIFACTU_ROTA", e, Severidad.ERROR)

    def revisar_numeracion(self) -> None:
        series = defaultdict(list)
        for f in self.libro.facturas_de(Direccion.EMITIDA):
            if f.numero.isdigit() and f.estado != EstadoFactura.BORRADOR:
                series[f.serie].append(int(f.numero))
        for serie, nums in series.items():
            nums.sort()
            huecos = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums))
            if huecos:
                self.incidencia("NUMERACION_CON_HUECOS", f"Serie {serie}: faltan los números {huecos}", Severidad.ERROR, serie)
            if len(nums) != len(set(nums)):
                self.incidencia("NUMERACION_DUPLICADA", f"Serie {serie}: números duplicados", Severidad.ERROR, serie)

    def revisar_envios(self) -> None:
        for r in self.ctx.verifactu.registros():
            if r.estado_envio == "rechazado":
                self.incidencia("REGISTRO_RECHAZADO", f"Registro {r.num_serie} rechazado por la AEAT: subsanar", Severidad.ERROR, str(r.secuencia))
