"""Libro contable: estado compartido del negocio que consultan los agentes.

Implementación en memoria con exportación a JSON. Los registros VeriFactu,
que sí deben ser inalterables y persistentes, viven en ``SistemaVeriFactu``.
"""
from __future__ import annotations

import json
import os
import pickle
from datetime import date
from typing import Dict, Iterable, List, Optional

from .models import (
    Direccion,
    EmailSaliente,
    EstadoFactura,
    EstadoFaltante,
    Factura,
    FacturaFaltante,
    Incidencia,
    MovimientoBancario,
    Tercero,
    a_dict,
)
from .verifactu.validaciones import normalizar_nif


class Libro:
    def __init__(self, nif_empresa: str, nombre_empresa: str, email_empresa: str = "") -> None:
        self.nif_empresa = normalizar_nif(nif_empresa)
        self.nombre_empresa = nombre_empresa
        self.email_empresa = email_empresa
        self.terceros: Dict[str, Tercero] = {}
        self.facturas: Dict[str, Factura] = {}
        self.movimientos: Dict[str, MovimientoBancario] = {}
        self.faltantes: Dict[str, FacturaFaltante] = {}
        self.incidencias: Dict[str, Incidencia] = {}
        self.emails: List[EmailSaliente] = []
        # Memoria entre ejecuciones para no reprocesar ni duplicar acciones
        self.documentos_vistos: set = set()
        self.claves_bancarias: set = set()
        self.recordatorios_cobro: Dict[str, date] = {}

    # ------------------------------------------------------ persistencia
    def guardar(self, ruta: str) -> None:
        """Guarda el estado completo (fichero local de confianza)."""
        tmp = ruta + ".tmp"
        with open(tmp, "wb") as fh:
            pickle.dump(self, fh)
        os.replace(tmp, ruta)

    @staticmethod
    def cargar(ruta: str) -> "Libro":
        with open(ruta, "rb") as fh:
            return pickle.load(fh)

    # ------------------------------------------------------------ terceros
    def alta_tercero(self, t: Tercero) -> Tercero:
        t.nif = normalizar_nif(t.nif)
        existente = self.tercero_por_nif(t.nif)
        if existente:
            return existente
        self.terceros[t.id] = t
        return t

    def tercero_por_nif(self, nif: Optional[str]) -> Optional[Tercero]:
        n = normalizar_nif(nif or "")
        return next((t for t in self.terceros.values() if t.nif == n), None)

    def tercero_por_texto(self, texto: str) -> Optional[Tercero]:
        """Identifica un tercero a partir de un concepto bancario o texto libre."""
        tx = texto.upper()
        for t in self.terceros.values():
            claves = [t.nombre.upper(), t.nif] + [a.upper() for a in t.alias_bancarios]
            if any(c and c in tx for c in claves):
                return t
        return None

    # ------------------------------------------------------------ facturas
    def anadir_factura(self, f: Factura) -> Factura:
        self.facturas[f.id] = f
        return f

    def facturas_de(self, direccion: Direccion) -> List[Factura]:
        return [f for f in self.facturas.values() if f.direccion == direccion]

    def buscar_factura(self, emisor_nif: str, num_serie: str) -> Optional[Factura]:
        n = normalizar_nif(emisor_nif)
        return next(
            (f for f in self.facturas.values() if normalizar_nif(f.emisor_nif) == n and f.num_serie == num_serie),
            None,
        )

    def recibidas_de(self, nif: str, desde: Optional[date] = None, hasta: Optional[date] = None) -> List[Factura]:
        n = normalizar_nif(nif)
        out = []
        for f in self.facturas_de(Direccion.RECIBIDA):
            if normalizar_nif(f.emisor_nif) != n or f.estado == EstadoFactura.ANULADA:
                continue
            if desde and f.fecha < desde:
                continue
            if hasta and f.fecha > hasta:
                continue
            out.append(f)
        return out

    def siguiente_numero(self, serie: str) -> str:
        nums = [
            int(f.numero) for f in self.facturas_de(Direccion.EMITIDA)
            if f.serie == serie and f.numero.isdigit() and f.estado != EstadoFactura.BORRADOR
        ]
        return f"{(max(nums) + 1) if nums else 1:05d}"

    # --------------------------------------------------------- faltantes
    def faltantes_abiertas(self) -> List[FacturaFaltante]:
        return [x for x in self.faltantes.values() if x.estado != EstadoFaltante.RESUELTA]

    def faltante_existente(self, proveedor_nif: Optional[str], periodo: Optional[str], movimiento_id: Optional[str]) -> Optional[FacturaFaltante]:
        for x in self.faltantes.values():
            if movimiento_id and x.movimiento_id == movimiento_id:
                return x
            if not movimiento_id and x.proveedor_nif == proveedor_nif and x.periodo == periodo:
                return x
        return None

    # ------------------------------------------------------------ export
    def resumen(self) -> Dict[str, int]:
        return {
            "terceros": len(self.terceros),
            "facturas_emitidas": len(self.facturas_de(Direccion.EMITIDA)),
            "facturas_recibidas": len(self.facturas_de(Direccion.RECIBIDA)),
            "movimientos": len(self.movimientos),
            "movimientos_sin_conciliar": sum(1 for m in self.movimientos.values() if not m.factura_id),
            "faltantes_abiertas": len(self.faltantes_abiertas()),
            "incidencias_abiertas": sum(1 for i in self.incidencias.values() if not i.resuelta),
            "emails_enviados": len(self.emails),
        }

    def exportar_json(self, ruta: str) -> None:
        def lista(xs: Iterable) -> list:
            return [a_dict(x) for x in xs]

        datos = {
            "empresa": {"nif": self.nif_empresa, "nombre": self.nombre_empresa},
            "terceros": lista(self.terceros.values()),
            "facturas": lista(self.facturas.values()),
            "movimientos": lista(self.movimientos.values()),
            "faltantes": lista(self.faltantes.values()),
            "incidencias": lista(self.incidencias.values()),
            "emails": lista(self.emails),
        }
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(datos, fh, ensure_ascii=False, indent=2)
