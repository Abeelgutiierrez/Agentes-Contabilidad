"""Cálculo de la huella (hash) encadenada de los registros VeriFactu.

Según la especificación técnica de la AEAT ("Detalle de las especificaciones
técnicas para generación de la huella o hash de los registros de facturación"),
la huella es el SHA-256, en hexadecimal y mayúsculas, de una cadena
``campo=valor`` unida por ``&`` con los campos del registro y la huella del
registro anterior (vacía en el primer registro del sistema).
"""
from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


def formatear_fecha(d: date) -> str:
    """Las fechas de expedición se expresan como dd-mm-aaaa."""
    return d.strftime("%d-%m-%Y")


def formatear_importe(valor: Decimal) -> str:
    return f"{Decimal(valor):.2f}"


def formatear_fecha_hora_huso(momento: datetime) -> str:
    """ISO 8601 con huso horario, p.ej. 2024-01-01T19:20:30+01:00."""
    if momento.tzinfo is None:
        raise ValueError("FechaHoraHusoGenRegistro debe incluir zona horaria")
    return momento.replace(microsecond=0).isoformat()


def _sha256(cadena: str) -> str:
    return hashlib.sha256(cadena.encode("utf-8")).hexdigest().upper()


def huella_alta(
    nif_emisor: str,
    num_serie: str,
    fecha_expedicion: date,
    tipo_factura: str,
    cuota_total: Decimal,
    importe_total: Decimal,
    huella_anterior: Optional[str],
    fecha_hora_huso: datetime,
) -> str:
    """Huella de un registro de alta (RegistroAlta)."""
    partes = [
        ("IDEmisorFactura", nif_emisor.strip()),
        ("NumSerieFactura", num_serie.strip()),
        ("FechaExpedicionFactura", formatear_fecha(fecha_expedicion)),
        ("TipoFactura", tipo_factura.strip()),
        ("CuotaTotal", formatear_importe(cuota_total)),
        ("ImporteTotal", formatear_importe(importe_total)),
        ("Huella", (huella_anterior or "").strip()),
        ("FechaHoraHusoGenRegistro", formatear_fecha_hora_huso(fecha_hora_huso)),
    ]
    return _sha256("&".join(f"{k}={v}" for k, v in partes))


def huella_anulacion(
    nif_emisor: str,
    num_serie: str,
    fecha_expedicion: date,
    huella_anterior: Optional[str],
    fecha_hora_huso: datetime,
) -> str:
    """Huella de un registro de anulación (RegistroAnulacion)."""
    partes = [
        ("IDEmisorFacturaAnulada", nif_emisor.strip()),
        ("NumSerieFacturaAnulada", num_serie.strip()),
        ("FechaExpedicionFacturaAnulada", formatear_fecha(fecha_expedicion)),
        ("Huella", (huella_anterior or "").strip()),
        ("FechaHoraHusoGenRegistro", formatear_fecha_hora_huso(fecha_hora_huso)),
    ]
    return _sha256("&".join(f"{k}={v}" for k, v in partes))
