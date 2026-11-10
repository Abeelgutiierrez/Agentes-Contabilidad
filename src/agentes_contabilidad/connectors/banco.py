"""Movimientos bancarios desde CSV (exportación estándar de cualquier banco).

Formato esperado (cabecera obligatoria, separador ``;`` o ``,``)::

    fecha;concepto;importe
    2026-10-03;RECIBO IBERDROLA CLIENTES;-84,70

Para conexión directa con el banco se puede implementar ``FuenteBancaria``
sobre un agregador PSD2 (GoCardless/Nordigen, Tink, Salt Edge...).
"""
from __future__ import annotations

import csv
from datetime import date, datetime
from typing import List, Set

from ..models import MovimientoBancario, dinero


def _fecha(txt: str) -> date:
    txt = txt.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    raise ValueError(f"Fecha no reconocida: {txt}")


def _importe(txt: str):
    t = txt.strip().replace(" ", "").replace("€", "")
    if "," in t and "." in t:  # 1.234,56
        t = t.replace(".", "").replace(",", ".")
    return dinero(t.replace(",", "."))


class BancoCSV:
    def __init__(self, ruta: str, cuenta: str = "principal") -> None:
        self.ruta = ruta
        self.cuenta = cuenta
        self._vistos: Set[tuple] = set()

    def movimientos(self) -> List[MovimientoBancario]:
        with open(self.ruta, encoding="utf-8-sig") as fh:
            muestra = fh.read(2048)
            fh.seek(0)
            delim = ";" if muestra.count(";") >= muestra.count(",") else ","
            out = []
            for fila in csv.DictReader(fh, delimiter=delim):
                clave = (fila["fecha"], fila["concepto"], fila["importe"])
                if clave in self._vistos:
                    continue
                self._vistos.add(clave)
                out.append(MovimientoBancario(
                    fecha=_fecha(fila["fecha"]), concepto=fila["concepto"].strip(),
                    importe=_importe(fila["importe"]), cuenta=self.cuenta,
                ))
            return out
