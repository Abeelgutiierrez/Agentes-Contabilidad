"""Servidor local del panel visual "La Oficina".

Solo usa la biblioteca estándar. Escucha únicamente en 127.0.0.1: el panel
es para el dueño del negocio en su propio ordenador.

API (JSON):
    GET  /api/info                  empresa, participantes, fases, modo
    GET  /api/eventos?desde=N       tráfico entre agentes a partir del evento N
    GET  /api/estado                lo que hay en "tu mesa": faltas, notas, VeriFactu, IVA
    POST /api/jornada   {fecha?}    ejecuta una jornada completa
    POST /api/venta     {cliente_nif, cliente_nombre, lineas:[...]}
    POST /api/llega-factura         (demo) entra una factura que faltaba
    POST /api/resolver  {id}        marca una nota de tu mesa como revisada
"""
from __future__ import annotations

import json
import mimetypes
import threading
import webbrowser
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlparse

from ..bus import Temas
from ..models import Direccion, Factura, LineaFactura
from ..trazas import NOMBRES_FASE, Trazador, _faltante, _incidencia, eur, participantes
from ..verifactu.validaciones import validar_nif

ESTATICOS = Path(__file__).resolve().parent / "static"


class Sesion:
    """Un ecosistema en marcha + su trazador, protegido por un cerrojo."""

    def __init__(self, orq, modo: str, trabajo: Optional[Path] = None) -> None:
        self.orq = orq
        self.modo = modo
        self.trabajo = trabajo
        self.lock = threading.RLock()
        self.trazador = Trazador(orq.ctx.bus, orq.ctx.hoy)
        self.ultimo_informe: Optional[Dict[str, Any]] = None
        orq.ctx.bus.suscribir(Temas.INFORME_FISCAL, self._on_informe)

    def _on_informe(self, msg) -> None:
        inf = msg.datos["informe"]
        self.ultimo_informe = {"trimestre": inf.trimestre, "anio": inf.anio, "repercutido": eur(inf.total_repercutido),
                               "soportado": eur(inf.total_soportado), "resultado": eur(inf.resultado_303),
                               "a_pagar": inf.resultado_303 > 0, "plazo": inf.plazo.strftime("%d/%m/%Y"),
                               "avisos": list(inf.avisos)}

    # ------------------------------------------------------------- lectura
    def info(self) -> Dict[str, Any]:
        lb = self.orq.ctx.libro
        return {
            "modo": self.modo,
            "empresa": {"nombre": lb.nombre_empresa, "nif": lb.nif_empresa},
            "hoy": self.orq.ctx.hoy.isoformat(),
            "participantes": participantes(self.orq),
            "fases": [{"id": f, "nombre": NOMBRES_FASE[f]} for f in self.orq.FASES],
            "clientes": [{"nif": t.nif, "nombre": t.nombre} for t in lb.terceros.values() if t.es_cliente],
            "ia": self.orq.ctx.llm.disponible,
        }

    def estado(self) -> Dict[str, Any]:
        with self.lock:
            return self._estado()

    def _estado(self) -> Dict[str, Any]:
        ctx = self.orq.ctx
        lb = ctx.libro
        regs = ctx.verifactu.registros()
        emitidas = lb.facturas_de(Direccion.EMITIDA)
        recibidas = lb.facturas_de(Direccion.RECIBIDA)
        return {
            "hoy": ctx.hoy.isoformat(),
            "resumen": lb.resumen(),
            "faltantes": [_faltante(x) for x in lb.faltantes_abiertas()],
            "incidencias": [_incidencia(i) for i in lb.incidencias.values() if not i.resuelta],
            "verifactu": {
                "registros": len(regs),
                "integra": not ctx.verifactu.verificar_cadena(),
                "cadena": [{"numero": r.num_serie, "tipo": r.tipo_registro, "huella": r.huella,
                            "envio": r.estado_envio, "total": eur(r.importe_total)} for r in regs[-8:]],
            },
            "totales": {
                "ventas": eur(sum((f.importe_total for f in emitidas), Decimal(0))),
                "compras": eur(sum((f.importe_total for f in recibidas), Decimal(0))),
            },
            "informe": self.ultimo_informe,
            "por_llegar": len(self._por_llegar()),
            "emails": len(lb.emails),
        }

    def _por_llegar(self):
        if self.modo != "demo" or not self.trabajo:
            return []
        from ..demo import facturas_por_llegar

        return facturas_por_llegar(self.trabajo)

    # ------------------------------------------------------------ acciones
    def jornada(self, fecha: Optional[str]) -> Dict[str, Any]:
        with self.lock:
            dia = date.fromisoformat(fecha) if fecha else self.orq.ctx.hoy
            self.orq.ciclo(dia)
            # La siguiente jornada será el día siguiente
            self.orq.ctx.hoy = dia + timedelta(days=1)
            return {"ok": True, "jornada": dia.isoformat(), "siguiente": self.orq.ctx.hoy.isoformat()}

    def venta(self, datos: Dict[str, Any]) -> Dict[str, Any]:
        nif = (datos.get("cliente_nif") or "").strip().upper()
        nombre = (datos.get("cliente_nombre") or "").strip()
        lineas = []
        try:
            for l in datos.get("lineas") or []:
                desc = str(l.get("descripcion", "")).strip()
                if not desc:
                    continue
                lineas.append(LineaFactura(desc, Decimal(str(l.get("cantidad", 1))),
                                           Decimal(str(l.get("precio_unitario", "0")).replace(",", ".")),
                                           Decimal(str(l.get("tipo_iva", 21)))))
        except (InvalidOperation, ValueError):
            return {"ok": False, "error": "Revisa los importes: usa números como 12,50."}
        if not lineas:
            return {"ok": False, "error": "Añade al menos una línea con descripción y precio."}
        with self.lock:
            hoy = self.orq.ctx.hoy
            self.trazador.fijar_dia(hoy)
            f = Factura(numero="", serie="", fecha=hoy, direccion=Direccion.EMITIDA, emisor_nif="", emisor_nombre="",
                        receptor_nif=nif or None, receptor_nombre=nombre or nif, lineas=lineas)
            ok = self.orq.emitir_factura(f)
        if ok:
            return {"ok": True, "numero": f.num_serie, "total": eur(f.importe_total)}
        motivo = "El NIF del cliente no es válido." if not validar_nif(nif) else "El emisor la ha rechazado: mira la nota en tu mesa."
        return {"ok": False, "error": motivo}

    def llega_factura(self) -> Dict[str, Any]:
        if self.modo != "demo" or not self.trabajo:
            return {"ok": False, "error": "Solo disponible en la demo. Con tus datos, deja la factura en tu carpeta de entrada."}
        from ..demo import entregar_factura

        with self.lock:
            self.trazador.fijar_dia(self.orq.ctx.hoy)
            nombre = entregar_factura(self.trabajo)
            if not nombre:
                return {"ok": False, "error": "Ya no quedan facturas por llegar en la demo."}
            # Recepción la recoge al momento (y el resto del equipo reacciona)
            self.orq.ejecutar_fase("ingesta")
        return {"ok": True, "documento": nombre}

    def resolver(self, inc_id: str) -> Dict[str, Any]:
        with self.lock:
            self.trazador.fijar_dia(self.orq.ctx.hoy)
            ok = self.orq.resolver_incidencia(inc_id)
        return {"ok": ok} if ok else {"ok": False, "error": "Esa nota ya no está abierta."}


def crear_manejador(sesion: Sesion):
    class Manejador(BaseHTTPRequestHandler):
        server_version = "AgentesContabilidad/0.2"

        def log_message(self, fmt, *args):  # silencio: el panel ya enseña lo que pasa
            pass

        def _json(self, datos: Any, estado: int = 200) -> None:
            cuerpo = json.dumps(datos, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(estado)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def _cuerpo(self) -> Dict[str, Any]:
            n = int(self.headers.get("Content-Length") or 0)
            if not n:
                return {}
            try:
                return json.loads(self.rfile.read(n).decode("utf-8"))
            except json.JSONDecodeError:
                return {}

        def do_GET(self) -> None:
            url = urlparse(self.path)
            if url.path == "/api/info":
                return self._json(sesion.info())
            if url.path == "/api/estado":
                return self._json(sesion.estado())
            if url.path == "/api/eventos":
                desde = int(parse_qs(url.query).get("desde", ["0"])[0] or 0)
                return self._json({"eventos": sesion.trazador.desde(desde)})
            ruta = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
            fichero = (ESTATICOS / ruta).resolve()
            if ESTATICOS not in fichero.parents or not fichero.is_file():
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            datos = fichero.read_bytes()
            tipo = mimetypes.guess_type(fichero.name)[0] or "application/octet-stream"
            if tipo.startswith("text/") or tipo.endswith("javascript"):
                tipo += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", tipo)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Content-Length", str(len(datos)))
            self.end_headers()
            self.wfile.write(datos)

        def do_POST(self) -> None:
            url = urlparse(self.path)
            datos = self._cuerpo()
            try:
                if url.path == "/api/jornada":
                    return self._json(sesion.jornada(datos.get("fecha")))
                if url.path == "/api/venta":
                    return self._json(sesion.venta(datos))
                if url.path == "/api/llega-factura":
                    return self._json(sesion.llega_factura())
                if url.path == "/api/resolver":
                    return self._json(sesion.resolver(str(datos.get("id", ""))))
            except Exception as e:  # el panel muestra el error en lugar de quedarse colgado
                return self._json({"ok": False, "error": f"Error interno: {e}"}, 500)
            self.send_error(HTTPStatus.NOT_FOUND)

    return Manejador


def arrancar(orq, modo: str, trabajo: Optional[Path] = None, puerto: int = 8765, abrir: bool = True,
             preparar=None) -> None:
    sesion = Sesion(orq, modo, trabajo)
    if preparar:  # p.ej. la historia previa de la demo, para que se vea al abrir
        preparar(sesion)
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), crear_manejador(sesion))
    url = f"http://127.0.0.1:{puerto}/"
    print(f"\n  La Oficina está abierta en {url}")
    print("  (Ctrl+C para cerrar)\n")
    if abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\n  Oficina cerrada. ¡Hasta mañana!")
    finally:
        servidor.server_close()
