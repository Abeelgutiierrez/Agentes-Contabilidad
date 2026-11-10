"""Demostración de extremo a extremo con datos de ejemplo (sin red ni IA obligatoria).

Escenario: "Cafetería La Plaza SL" (empresa ficticia).
  * Día 10/11/2026: llegan facturas de proveedores y el extracto del banco.
    Se emiten dos facturas de venta con VeriFactu.
  * Día 18/11/2026: llega la factura que faltaba del software TPV.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

from .config import crear_ecosistema
from .models import Direccion, Factura, LineaFactura


def _carpeta_ejemplos() -> Path:
    for base in (Path(__file__).resolve().parents[2], Path.cwd()):
        p = base / "examples"
        if (p / "config.json").exists():
            return p
    raise FileNotFoundError("No se encuentra la carpeta 'examples' (ejecuta desde la raíz del repositorio)")


def _venta(cliente_nif: str, cliente: str, fecha: date, lineas) -> Factura:
    return Factura(numero="", serie="A", fecha=fecha, direccion=Direccion.EMITIDA, emisor_nif="", emisor_nombre="",
                   receptor_nif=cliente_nif, receptor_nombre=cliente,
                   lineas=[LineaFactura(d, Decimal(c), Decimal(p), Decimal(t)) for d, c, p, t in lineas])


def ejecutar(verbose: bool = True) -> "Orquestador":  # noqa: F821
    trabajo = Path(tempfile.mkdtemp(prefix="agentes_conta_demo_"))
    shutil.copytree(_carpeta_ejemplos(), trabajo, dirs_exist_ok=True)
    shutil.rmtree(trabajo / "datos_runtime", ignore_errors=True)
    orq = crear_ecosistema(str(trabajo / "config.json"))
    p = print if verbose else (lambda *a, **k: None)

    p("\n▶ Agentes del ecosistema:")
    for a in orq.describir():
        p(f"   • {a['nombre']:<17} {a['rol']}")

    # --- Ventas emitidas (cada una en su fecha real de expedición)
    orq.ctx.hoy = date(2026, 9, 20)
    orq.emitir_factura(_venta("B78901238", "Eventos Norte SL", date(2026, 9, 20),
                              [("Catering evento 80 pax", 80, "15.00", 10)]))
    orq.ctx.hoy = date(2026, 10, 15)
    orq.emitir_factura(_venta("B67890129", "Coworking Plaza SL", date(2026, 10, 15),
                              [("Desayunos de empresa octubre", 1, "500.00", 10)]))
    # Una venta mal formada: el agente emisor la rechaza
    orq.emitir_factura(_venta("B0000000X", "Cliente con NIF erróneo", date(2026, 10, 15),
                              [("Bocadillos", 10, "4.00", 10)]))

    p("\n▶ Ciclo del 10/11/2026")
    orq.ciclo(date(2026, 11, 10))
    p(orq.panel())

    p("\n▶ Llega por fin la factura del software TPV… ciclo del 18/11/2026")
    shutil.copy(trabajo / "datos" / "llegan_mas_tarde" / "tpv_cloud_oct.json",
                trabajo / "datos" / "bandeja_entrada" / "tpv_cloud_oct.json")
    orq.ciclo(date(2026, 11, 18))
    p(orq.panel())

    salida = trabajo / "datos_runtime" / "bandeja_salida"
    p(f"\n▶ Correos generados ({len(orq.ctx.libro.emails)}) en: {salida}")
    for e in orq.ctx.libro.emails[:3]:
        p(f"   → {e.para}: {e.asunto}")
    orq.ctx.libro.exportar_json(str(trabajo / "datos_runtime" / "libro.json"))
    p(f"\n▶ Estado completo exportado a {trabajo / 'datos_runtime' / 'libro.json'}")
    p(f"▶ Registros VeriFactu en {trabajo / 'datos_runtime' / 'verifactu.sqlite'}")
    os.environ["AGENTES_CONTA_DEMO_DIR"] = str(trabajo)
    return orq
