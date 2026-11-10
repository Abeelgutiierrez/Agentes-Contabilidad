import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from agentes_contabilidad.demo import emitir_historicas, preparar
from agentes_contabilidad.trazas import texto_plano
from agentes_contabilidad.web.servidor import Sesion, crear_manejador
from agentes_contabilidad.web.traza import traza_demo


def test_traza_demo_cuenta_la_historia():
    paquete = traza_demo()
    evs = paquete["eventos"]
    temas = [e["tema"] for e in evs]
    # El tráfico llega de fuera, pasa entre agentes y sale hacia fuera
    assert ("buzon", ["recepcion"]) in [(e["de"], e["a"]) for e in evs]
    assert any(e["de"] == "detective" and e["a"] == ["reclamador"] for e in evs)
    assert any(e["de"] == "reclamador" and e["a"] == ["proveedores"] and "email" in e["detalle"] for e in evs)
    assert any(e["tema"] == "aeat.envio" for e in evs)
    assert "factura.faltante_resuelta" in temas
    # Ids correlativos, cada evento con su día, textos sin huecos al pasarlos a consola
    assert [e["id"] for e in evs] == list(range(len(evs)))
    assert all(e["dia"] for e in evs)
    assert all("{" not in texto_plano(e) for e in evs)
    # Los participantes que aparecen están todos declarados
    ids = {p["id"] for p in paquete["info"]["participantes"]}
    assert all(e["de"] in ids and set(e["a"]) <= ids for e in evs)
    json.dumps(paquete, ensure_ascii=False, default=str)


@pytest.fixture
def servidor():
    orq, trabajo = preparar()
    sesion = Sesion(orq, "demo", trabajo)
    emitir_historicas(orq, sesion.trazador.fijar_dia)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), crear_manejador(sesion))
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()
    srv.server_close()


def _get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.status, r.read()


def _post(url, datos):
    req = urllib.request.Request(url, data=json.dumps(datos).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_api_de_la_oficina(servidor):
    estado, html = _get(servidor + "/")
    assert estado == 200 and b"La Oficina" in html
    info = json.loads(_get(servidor + "/api/info")[1])
    assert info["modo"] == "demo" and len(info["fases"]) == 8
    n0 = len(json.loads(_get(servidor + "/api/eventos?desde=0")[1])["eventos"])
    assert n0 == 8  # ventas históricas

    r = _post(servidor + "/api/jornada", {"fecha": "2026-11-10"})
    assert r["ok"] and r["siguiente"] == "2026-11-11"
    nuevos = json.loads(_get(servidor + f"/api/eventos?desde={n0}")[1])["eventos"]
    assert nuevos[0]["tema"] == "ciclo.iniciado" and nuevos[-1]["tema"] == "ciclo.terminado"

    venta = _post(servidor + "/api/venta", {"cliente_nif": "B67890129", "cliente_nombre": "Coworking Plaza SL",
                                            "lineas": [{"descripcion": "Catering", "cantidad": 2, "precio_unitario": "50", "tipo_iva": 10}]})
    assert venta["ok"] and venta["total"] == "110,00 €"
    mala = _post(servidor + "/api/venta", {"cliente_nif": "X", "lineas": [{"descripcion": "Algo", "precio_unitario": "1"}]})
    assert not mala["ok"] and "NIF" in mala["error"]

    llega = _post(servidor + "/api/llega-factura", {})
    assert llega["ok"]
    est = json.loads(_get(servidor + "/api/estado")[1])
    assert est["verifactu"]["integra"] and est["verifactu"]["registros"] == 3
    assert all(f["proveedor"] != "Software TPV Cloud SL" for f in est["faltantes"])  # la factura que llegó cierra la falta

    inc = est["incidencias"][0]["id"]
    assert _post(servidor + "/api/resolver", {"id": inc})["ok"]
    assert not _post(servidor + "/api/resolver", {"id": inc})["ok"]


def test_no_sirve_ficheros_fuera_de_static(servidor):
    with pytest.raises(urllib.error.HTTPError):
        _get(servidor + "/../servidor.py")
