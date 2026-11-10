"""Agente Detective: siempre sabe qué facturas faltan.

Reglas:
1. **Pago sin factura**: un cargo bancario que pasados ``dias_gracia_factura``
   sigue sin conciliar con ninguna factura recibida.
2. **Recurrente no recibida**: un proveedor marcado como recurrente (alquiler,
   suministros, software...) del que no hay factura en el mes anterior.

Cuando la factura llega (y el conciliador la casa con el pago), el detective
marca la falta como resuelta automáticamente.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional, Tuple

from ..bus import Mensaje, Temas
from ..models import EstadoFaltante, Factura, FacturaFaltante, MovimientoBancario
from ..verifactu.validaciones import normalizar_nif
from .base import Agente


def mes_anterior(hoy: date) -> Tuple[date, date, str]:
    fin = hoy.replace(day=1) - timedelta(days=1)
    ini = fin.replace(day=1)
    return ini, fin, ini.strftime("%Y-%m")


class AgenteFacturasFaltantes(Agente):
    nombre = "detective"
    rol = "Detecta las facturas de proveedores que faltan y las comunica al reclamador."
    fases = ("deteccion",)

    def suscribir(self) -> None:
        self.escuchar(Temas.MOVIMIENTO_CONCILIADO, self._on_conciliado)
        self.escuchar(Temas.FACTURA_RECIBIDA, self._on_factura)

    def ejecutar_fase(self, fase: str) -> None:
        self.detectar_pagos_sin_factura()
        self.detectar_recurrentes()

    # ---------------------------------------------------------- reglas
    def _sin_factura_esperada(self, mov: MovimientoBancario) -> bool:
        concepto = mov.concepto.upper()
        return any(k in concepto for k in self.ctx.politicas.conceptos_sin_factura)

    def detectar_pagos_sin_factura(self) -> None:
        limite = self.ctx.hoy - timedelta(days=self.ctx.politicas.dias_gracia_factura)
        for mov in self.libro.movimientos.values():
            if not mov.es_cargo or mov.factura_id or mov.fecha > limite or self._sin_factura_esperada(mov):
                continue
            if self.libro.faltante_existente(None, None, mov.id):
                continue
            t = self.libro.tercero_por_texto(mov.concepto)
            self._registrar(FacturaFaltante(
                motivo=f"Pago de {abs(mov.importe)} € el {mov.fecha:%d/%m/%Y} sin factura ('{mov.concepto}')",
                proveedor_nif=t.nif if t else None,
                proveedor_nombre=t.nombre if t else mov.concepto,
                importe_estimado=abs(mov.importe),
                periodo=mov.fecha.strftime("%Y-%m"),
                movimiento_id=mov.id,
            ))

    def detectar_recurrentes(self) -> None:
        ini, fin, periodo = mes_anterior(self.ctx.hoy)
        for t in self.libro.terceros.values():
            if not (t.es_proveedor and t.recurrente):
                continue
            if self.libro.recibidas_de(t.nif, ini, fin):
                continue
            ya = any(x.proveedor_nif == t.nif and x.periodo == periodo for x in self.libro.faltantes.values())
            if ya:
                continue
            self._registrar(FacturaFaltante(
                motivo=f"Proveedor recurrente sin factura de {periodo}",
                proveedor_nif=t.nif, proveedor_nombre=t.nombre, periodo=periodo,
            ))

    def _registrar(self, f: FacturaFaltante) -> None:
        self.libro.faltantes[f.id] = f
        self.log.info("Falta factura: %s — %s", f.proveedor_nombre, f.motivo)
        self.publicar(Temas.FACTURA_FALTANTE, faltante=f)

    # ------------------------------------------------------ resolución
    def _resolver(self, faltante: FacturaFaltante, factura: Factura) -> None:
        faltante.estado = EstadoFaltante.RESUELTA
        self.log.info("Resuelta falta de %s con %s", faltante.proveedor_nombre, factura.num_serie)
        self.publicar(Temas.FACTURA_FALTANTE_RESUELTA, faltante=faltante, factura=factura)

    def _on_conciliado(self, msg: Mensaje) -> None:
        mov: MovimientoBancario = msg.datos["movimiento"]
        for x in self.libro.faltantes_abiertas():
            if x.movimiento_id == mov.id:
                self._resolver(x, msg.datos["factura"])

    def _on_factura(self, msg: Mensaje) -> None:
        f: Factura = msg.datos["factura"]
        periodo = f.fecha.strftime("%Y-%m")
        for x in self.libro.faltantes_abiertas():
            if x.movimiento_id is None and x.proveedor_nif == normalizar_nif(f.emisor_nif) and x.periodo == periodo:
                self._resolver(x, f)

    def faltante_de(self, nif: str) -> Optional[FacturaFaltante]:
        return next((x for x in self.libro.faltantes_abiertas() if x.proveedor_nif == nif), None)
