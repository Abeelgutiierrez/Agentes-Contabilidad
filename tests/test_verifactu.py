import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from agentes_contabilidad.models import Direccion, Factura, LineaFactura
from agentes_contabilidad.verifactu import SistemaVeriFactu, huella_alta, url_qr, validar_nif

TZ = timezone(timedelta(hours=1))


def test_huella_ejemplo_oficial_aeat():
    # Ejemplo publicado por la AEAT en la especificación de la huella
    h = huella_alta("89890001K", "12345678/G33", date(2024, 1, 1), "F1", Decimal("12.35"),
                    Decimal("123.45"), None, datetime(2024, 1, 1, 19, 20, 30, tzinfo=TZ))
    assert h == "3C464DAF61ACB827C65FDA19F352A4E3BDC2C640E9E9FC4CC058073F38F12F60"


def test_huella_exige_zona_horaria():
    with pytest.raises(ValueError):
        huella_alta("B12345674", "A1", date(2026, 1, 1), "F1", Decimal(1), Decimal(2), None, datetime(2026, 1, 1))


def _factura(num: str, total: str = "100") -> Factura:
    return Factura(numero=num, serie="A", fecha=date(2026, 11, 10), direccion=Direccion.EMITIDA,
                   emisor_nif="B12345674", emisor_nombre="Empresa", receptor_nif="B23456783",
                   receptor_nombre="Cliente", lineas=[LineaFactura("x", Decimal(1), Decimal(total), Decimal(21))])


def test_cadena_encadena_y_verifica():
    vf = SistemaVeriFactu(tz=TZ)
    r1 = vf.registrar_alta(_factura("1"))
    r2 = vf.registrar_alta(_factura("2"))
    r3 = vf.registrar_anulacion(_factura("1"))
    assert r1.huella_anterior is None
    assert r2.huella_anterior == r1.huella
    assert r3.huella_anterior == r2.huella
    assert "PrimerRegistro" in r1.xml and r1.huella in r2.xml
    assert vf.verificar_cadena() == []


def test_no_permite_duplicar_alta_ni_anular_inexistente():
    vf = SistemaVeriFactu(tz=TZ)
    vf.registrar_alta(_factura("1"))
    with pytest.raises(ValueError):
        vf.registrar_alta(_factura("1"))
    with pytest.raises(ValueError):
        vf.registrar_anulacion(_factura("99"))


def test_registros_inalterables_y_manipulacion_detectada(tmp_path):
    ruta = str(tmp_path / "vf.sqlite")
    vf = SistemaVeriFactu(ruta, tz=TZ)
    vf.registrar_alta(_factura("1"))
    vf.registrar_alta(_factura("2"))
    with pytest.raises(sqlite3.DatabaseError):
        vf.conn.execute("UPDATE registros SET importe_total='1.00' WHERE secuencia=1")
    with pytest.raises(sqlite3.DatabaseError):
        vf.conn.execute("DELETE FROM registros")
    # Un atacante que salta los triggers queda igualmente en evidencia
    vf.conn.execute("DROP TRIGGER no_modificar")
    vf.conn.execute("UPDATE registros SET importe_total='1.00' WHERE secuencia=1")
    errores = vf.verificar_cadena()
    assert errores and "alterada" in errores[0]


def test_url_qr():
    u = url_qr("B12345674", "A 0001", date(2026, 11, 10), Decimal("121"))
    assert u.startswith("https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?")
    assert "numserie=A+0001" in u and "fecha=10-11-2026" in u and "importe=121.00" in u


@pytest.mark.parametrize("nif,ok", [
    ("12345678Z", True), ("12345678A", False), ("X1234567L", True), ("B12345674", True),
    ("B12345675", False), ("ESB12345674", True), ("Q2826000H", True), ("", False), ("B0000000X", False),
])
def test_validar_nif(nif, ok):
    assert validar_nif(nif) is ok
