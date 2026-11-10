"""Demostración de extremo a extremo con datos de ejemplo (sin red ni IA obligatoria).

Escenario: "Cafetería La Plaza SL" (empresa ficticia).
  * Ventas de septiembre y octubre emitidas con VeriFactu.
  * Día 10/11/2026: llegan facturas de proveedores y el extracto del banco.
  * Día 18/11/2026: llega la factura que faltaba del software TPV.
"""
from __future__ import annotations

import shutil
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Tuple

from .config import crear_ecosistema
from .models import Direccion, Factura, LineaFactura

DIA_INICIO = date(2026, 11, 10)


def carpeta_ejemplos() -> Path:
    for base in (Path(__file__).resolve().parents[2], Path.cwd()):
        p = base / "examples"
        if (p / "config.json").exists():
            return p
    raise FileNotFoundError("No se encuentra la carpeta 'examples' (ejecuta desde la raíz del repositorio)")


def venta(cliente_nif: str, cliente: str, fecha: date, lineas) -> Factura:
    return Factura(numero="", serie="A", fecha=fecha, direccion=Direccion.EMITIDA, emisor_nif="", emisor_nombre="",
                   receptor_nif=cliente_nif, receptor_nombre=cliente,
                   lineas=[LineaFactura(d, Decimal(str(c)), Decimal(str(p)), Decimal(str(t))) for d, c, p, t in lineas])


# Ventas previas del escenario: (fecha, nif, cliente, líneas)
VENTAS_HISTORICAS: List[Tuple[date, str, str, list]] = [
    (date(2026, 9, 20), "B78901238", "Eventos Norte SL", [("Catering evento 80 pax", 80, "15.00", 10)]),
    (date(2026, 10, 15), "B67890129", "Coworking Plaza SL", [("Desayunos de empresa octubre", 1, "500.00", 10)]),
    # Venta mal formada a propósito: el emisor la rechaza
    (date(2026, 10, 15), "B0000000X", "Cliente con NIF erróneo", [("Bocadillos", 10, "4.00", 10)]),
]


def preparar(trabajo: Optional[Path] = None):
    """Copia los datos de ejemplo a una carpeta temporal y monta el ecosistema."""
    trabajo = trabajo or Path(tempfile.mkdtemp(prefix="agentes_conta_demo_"))
    shutil.copytree(carpeta_ejemplos(), trabajo, dirs_exist_ok=True)
    shutil.rmtree(trabajo / "datos_runtime", ignore_errors=True)
    return crear_ecosistema(str(trabajo / "config.json")), trabajo


def emitir_historicas(orq, al_cambiar_dia=None) -> None:
    for fecha, nif, nombre, lineas in VENTAS_HISTORICAS:
        orq.ctx.hoy = fecha
        if al_cambiar_dia:
            al_cambiar_dia(fecha)
        orq.emitir_factura(venta(nif, nombre, fecha, lineas))
    orq.ctx.hoy = DIA_INICIO


def facturas_por_llegar(trabajo: Path) -> List[Path]:
    return sorted((trabajo / "datos" / "llegan_mas_tarde").glob("*"))


def entregar_factura(trabajo: Path) -> Optional[str]:
    """Mueve la siguiente factura "que llega más tarde" a la bandeja de entrada."""
    pendientes = facturas_por_llegar(trabajo)
    if not pendientes:
        return None
    destino = trabajo / "datos" / "bandeja_entrada" / pendientes[0].name
    shutil.move(str(pendientes[0]), destino)
    return destino.name


def escenario_completo(orq, trabajo: Path, trazador=None) -> None:
    """Todo el guion de la demo: ventas, dos jornadas y una factura que llega tarde."""
    emitir_historicas(orq, trazador.fijar_dia if trazador else None)
    orq.ciclo(DIA_INICIO)
    entregar_factura(trabajo)
    orq.ciclo(date(2026, 11, 18))


def ejecutar(verbose: bool = True):
    orq, trabajo = preparar()
    p = print if verbose else (lambda *a, **k: None)

    p("\n▶ Agentes del ecosistema:")
    for a in orq.describir():
        p(f"   • {a['nombre']:<17} {a['rol']}")

    emitir_historicas(orq)
    p(f"\n▶ Ciclo del {DIA_INICIO:%d/%m/%Y}")
    orq.ciclo(DIA_INICIO)
    p(orq.panel())

    p("\n▶ Llega por fin la factura del software TPV… ciclo del 18/11/2026")
    entregar_factura(trabajo)
    orq.ciclo(date(2026, 11, 18))
    p(orq.panel())

    salida = trabajo / "datos_runtime" / "bandeja_salida"
    p(f"\n▶ Correos generados ({len(orq.ctx.libro.emails)}) en: {salida}")
    for e in orq.ctx.libro.emails[:3]:
        p(f"   → {e.para}: {e.asunto}")
    orq.ctx.libro.exportar_json(str(trabajo / "datos_runtime" / "libro.json"))
    p(f"\n▶ Estado completo exportado a {trabajo / 'datos_runtime' / 'libro.json'}")
    p(f"▶ Registros VeriFactu en {trabajo / 'datos_runtime' / 'verifactu.sqlite'}")
    p("\n▶ Para verlo como una oficina animada: agentes-conta web --demo")
    return orq
