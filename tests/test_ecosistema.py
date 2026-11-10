import json
import shutil
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from agentes_contabilidad import Temas, crear_ecosistema
from agentes_contabilidad.agents.recepcion import AgenteRecepcion
from agentes_contabilidad.models import Direccion, EstadoFactura, EstadoFaltante, Factura, LineaFactura

EJEMPLOS = Path(__file__).resolve().parents[1] / "examples"


@pytest.fixture
def entorno(tmp_path):
    shutil.copytree(EJEMPLOS, tmp_path, dirs_exist_ok=True)
    shutil.rmtree(tmp_path / "datos_runtime", ignore_errors=True)
    return tmp_path


def venta(nif, nombre, fecha, base="100", iva=21):
    return Factura(numero="", serie="A", fecha=fecha, direccion=Direccion.EMITIDA, emisor_nif="", emisor_nombre="",
                   receptor_nif=nif, receptor_nombre=nombre,
                   lineas=[LineaFactura("Servicio", Decimal(1), Decimal(base), Decimal(iva))])


def faltante_de(orq, nombre):
    return next(f for f in orq.ctx.libro.faltantes.values() if f.proveedor_nombre.startswith(nombre))


def test_ciclo_completo(entorno):
    orq = crear_ecosistema(str(entorno / "config.json"))
    orq.ctx.hoy = date(2026, 10, 15)
    assert orq.emitir_factura(venta("B67890129", "Coworking Plaza SL", date(2026, 10, 15), "500", 10))
    orq.ciclo(date(2026, 11, 10))
    lb = orq.ctx.libro

    # Recepción: 3 facturas válidas, la copia es duplicada, el menú no es factura
    assert len(lb.facturas_de(Direccion.RECIBIDA)) == 3
    codigos = {i.codigo for i in lb.incidencias.values()}
    assert {"FACTURA_DUPLICADA", "DOC_NO_RECONOCIDO", "TOTAL_INCOHERENTE"} <= codigos

    # Conciliación: café, electricidad y el cobro del coworking
    assert sum(1 for m in lb.movimientos.values() if m.factura_id) == 3
    assert lb.facturas_de(Direccion.EMITIDA)[0].estado == EstadoFactura.PAGADA

    # Detective: alquiler y TPV sin factura (nóminas y TGSS excluidas); marketplace escalado
    nombres = {f.proveedor_nombre for f in lb.faltantes_abiertas()}
    assert "Alquileres Centro SL" in nombres and "Software TPV Cloud SL" in nombres
    assert not any("NOMINA" in n or "TGSS" in n for n in nombres)
    assert faltante_de(orq, "COMPRA MARKETPLACE").estado == EstadoFaltante.ESCALADA

    # Reclamador: ha escrito al alquiler y al TPV
    destinatarios = {e.para for e in lb.emails}
    assert {"admin@alquilerescentro.example", "facturacion@tpvcloud.example"} <= destinatarios
    assert orq.ctx.bus.contar(Temas.RECLAMACION_ENVIADA) == 2

    # VeriFactu y fiscal
    assert orq.ctx.verifactu.verificar_cadena() == []
    assert orq.ctx.verifactu.pendientes_envio() == []  # remitido a la AEAT (simulada)
    assert orq.ultimo_informe is not None and orq.ultimo_informe.trimestre == 4


def test_factura_que_llega_resuelve_la_falta(entorno):
    orq = crear_ecosistema(str(entorno / "config.json"))
    orq.ciclo(date(2026, 11, 10))
    assert faltante_de(orq, "Software TPV").estado == EstadoFaltante.RECLAMADA
    shutil.copy(entorno / "datos/llegan_mas_tarde/tpv_cloud_oct.json", entorno / "datos/bandeja_entrada/")
    orq.ciclo(date(2026, 11, 12))
    assert faltante_de(orq, "Software TPV").estado == EstadoFaltante.RESUELTA


def test_reclamaciones_respetan_espera_y_escalan(entorno):
    orq = crear_ecosistema(str(entorno / "config.json"))
    orq.ciclo(date(2026, 11, 10))
    orq.ciclo(date(2026, 11, 12))  # antes de 7 días: no se reclama otra vez
    f = faltante_de(orq, "Alquileres")
    assert f.intentos == 1
    for d in (date(2026, 11, 18), date(2026, 11, 26), date(2026, 12, 4)):
        orq.ciclo(d)
    assert f.intentos == 3 and f.estado == EstadoFaltante.ESCALADA
    assert orq.ctx.bus.contar(Temas.ESCALADO_HUMANO) >= 2


def test_estado_persiste_entre_ejecuciones(entorno):
    cfg = str(entorno / "config.json")
    crear_ecosistema(cfg).ciclo(date(2026, 11, 10))
    orq = crear_ecosistema(cfg)
    n_emails = len(orq.ctx.libro.emails)
    orq.ciclo(date(2026, 11, 11))
    assert len(orq.ctx.libro.emails) == n_emails  # no repite correos ni reprocesa documentos
    assert len(orq.ctx.libro.facturas_de(Direccion.RECIBIDA)) == 3


def test_emisor_numera_y_rechaza_invalidas(entorno):
    orq = crear_ecosistema(str(entorno / "config.json"))
    orq.ctx.hoy = date(2026, 11, 10)
    a = venta("B67890129", "Coworking", date(2026, 11, 10))
    b = venta("B78901238", "Eventos", date(2026, 11, 10))
    assert orq.emitir_factura(a) and orq.emitir_factura(b)
    assert (a.num_serie, b.num_serie) == ("A00001", "A00002")
    assert not orq.emitir_factura(venta("B0000000X", "Malo", date(2026, 11, 10)))
    assert not orq.emitir_factura(venta("B67890129", "IVA raro", date(2026, 11, 10), iva=7))
    assert len(orq.ctx.verifactu.registros()) == 2


def test_extraccion_regex_de_texto():
    texto = (EJEMPLOS / "datos/bandeja_entrada/electrica_del_sur_oct.txt").read_text(encoding="utf-8")
    d = AgenteRecepcion._extraer_regex(texto)
    assert d["numero"] == "E-88123"
    assert d["fecha"] == "31/10/2026"
    assert d["emisor"]["nif"] == "B34567891"
    assert d["receptor"]["nif"] == "B12345674"
    assert d["total"] == "84,70" and d["tipo_iva"] == "21"
