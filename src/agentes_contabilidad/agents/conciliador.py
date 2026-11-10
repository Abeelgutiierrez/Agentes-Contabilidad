"""Agente Conciliador: empareja movimientos bancarios con facturas."""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from ..bus import Mensaje, Temas
from ..models import Direccion, EstadoFactura, Factura, MovimientoBancario
from ..verifactu.validaciones import normalizar_nif
from .base import Agente


class AgenteConciliador(Agente):
    nombre = "conciliador"
    rol = "Importa el banco y casa cada cobro/pago con su factura."
    fases = ("banco",)

    def suscribir(self) -> None:
        self.escuchar(Temas.FACTURA_RECIBIDA, self._on_factura)
        self.escuchar(Temas.FACTURA_EMITIDA, self._on_factura)
        self.escuchar(Temas.MOVIMIENTO_BANCARIO, self._on_movimiento)

    def ejecutar_fase(self, fase: str) -> None:
        for fuente in self.ctx.banco:
            for mov in fuente.movimientos():
                clave = (mov.cuenta, mov.fecha.isoformat(), mov.concepto, str(mov.importe))
                if clave in self.libro.claves_bancarias:
                    continue
                self.libro.claves_bancarias.add(clave)
                self.libro.movimientos[mov.id] = mov
                self.publicar(Temas.MOVIMIENTO_BANCARIO, movimiento=mov)

    def _on_movimiento(self, msg: Mensaje) -> None:
        mov: MovimientoBancario = msg.datos["movimiento"]
        if mov.factura_id:
            return
        f = self.buscar_factura(mov)
        if f:
            self._casar(mov, f)

    def _on_factura(self, msg: Mensaje) -> None:
        f: Factura = msg.datos["factura"]
        for mov in self.libro.movimientos.values():
            if not mov.factura_id and self._encaja(mov, f):
                self._casar(mov, f)
                return

    # ------------------------------------------------------------------
    def _candidatas(self, mov: MovimientoBancario) -> List[Factura]:
        direccion = Direccion.RECIBIDA if mov.es_cargo else Direccion.EMITIDA
        conciliadas = {m.factura_id for m in self.libro.movimientos.values() if m.factura_id}
        return [f for f in self.libro.facturas_de(direccion)
                if f.id not in conciliadas and f.estado not in (EstadoFactura.ANULADA, EstadoFactura.BORRADOR)]

    def _encaja(self, mov: MovimientoBancario, f: Factura) -> bool:
        if (f.direccion == Direccion.RECIBIDA) != mov.es_cargo:
            return False
        tol = Decimal(self.ctx.politicas.tolerancia_conciliacion)
        if abs(abs(mov.importe) - f.importe_total) > tol:
            return False
        return abs((mov.fecha - f.fecha).days) <= self.ctx.politicas.ventana_conciliacion_dias

    def buscar_factura(self, mov: MovimientoBancario) -> Optional[Factura]:
        posibles = [f for f in self._candidatas(mov) if self._encaja(mov, f)]
        if not posibles:
            return None
        tercero = self.libro.tercero_por_texto(mov.concepto)
        if tercero:
            nif_contraparte = (lambda f: f.emisor_nif) if mov.es_cargo else (lambda f: f.receptor_nif or "")
            preferidas = [f for f in posibles if normalizar_nif(nif_contraparte(f)) == tercero.nif]
            if preferidas:
                posibles = preferidas
            elif len(posibles) > 1:
                return None  # ambiguo: mejor no casar mal
        return min(posibles, key=lambda f: abs((mov.fecha - f.fecha).days))

    def _casar(self, mov: MovimientoBancario, f: Factura) -> None:
        mov.factura_id = f.id
        f.estado = EstadoFactura.PAGADA
        self.log.info("Conciliado %s %s € ↔ %s", mov.fecha, mov.importe, f.num_serie)
        self.publicar(Temas.MOVIMIENTO_CONCILIADO, movimiento=mov, factura=f)
