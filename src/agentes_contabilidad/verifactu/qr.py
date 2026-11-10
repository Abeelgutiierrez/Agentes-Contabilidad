"""Código QR tributario que debe imprimirse en cada factura VeriFactu.

El QR contiene una URL de cotejo de la AEAT con NIF, número de serie, fecha e
importe total. La imagen PNG requiere la dependencia opcional ``qrcode``.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from urllib.parse import urlencode

from .huella import formatear_fecha, formatear_importe

URL_PRODUCCION = "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQR"
URL_PRUEBAS = "https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR"
URL_PRODUCCION_NO_VERIFACTU = "https://www2.agenciatributaria.gob.es/wlpl/TIKE-CONT/ValidarQRNoVerifactu"


def url_qr(
    nif: str,
    num_serie: str,
    fecha: date,
    importe_total: Decimal,
    entorno: str = "pruebas",
    verifactu: bool = True,
) -> str:
    if entorno == "produccion":
        base = URL_PRODUCCION if verifactu else URL_PRODUCCION_NO_VERIFACTU
    else:
        base = URL_PRUEBAS if verifactu else URL_PRUEBAS + "NoVerifactu"
    params = {
        "nif": nif,
        "numserie": num_serie,
        "fecha": formatear_fecha(fecha),
        "importe": formatear_importe(importe_total),
    }
    return f"{base}?{urlencode(params)}"


def guardar_png(url: str, ruta: str) -> Optional[str]:
    """Genera el PNG del QR. Devuelve la ruta o ``None`` si falta ``qrcode``."""
    try:
        import qrcode  # type: ignore
    except ImportError:
        return None
    img = qrcode.make(url, error_correction=qrcode.constants.ERROR_CORRECT_M)
    img.save(ruta)
    return ruta
