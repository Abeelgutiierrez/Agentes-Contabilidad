"""Genera una traza grabada para ver el panel sin servidor (modo demostración)."""
from __future__ import annotations

import json
from datetime import date
from typing import Any, Dict, Optional

from ..trazas import NOMBRES_FASE, Trazador, participantes


def traza_demo() -> Dict[str, Any]:
    from ..demo import escenario_completo, preparar

    orq, trabajo = preparar()
    tz = Trazador(orq.ctx.bus)
    escenario_completo(orq, trabajo, tz)
    return _paquete(orq, tz, "grabacion")


def traza_config(config: str, fecha: Optional[str] = None) -> Dict[str, Any]:
    from ..config import crear_ecosistema

    orq = crear_ecosistema(config)
    tz = Trazador(orq.ctx.bus)
    orq.ciclo(date.fromisoformat(fecha) if fecha else None)
    return _paquete(orq, tz, "grabacion")


def _paquete(orq, tz: Trazador, modo: str) -> Dict[str, Any]:
    lb = orq.ctx.libro
    return {
        "info": {
            "modo": modo,
            "empresa": {"nombre": lb.nombre_empresa, "nif": lb.nif_empresa},
            "participantes": participantes(orq),
            "fases": [{"id": f, "nombre": NOMBRES_FASE[f]} for f in orq.FASES],
        },
        "eventos": tz.eventos,
    }


def guardar_traza(salida: str, demo: bool = False, config: Optional[str] = None, fecha: Optional[str] = None) -> int:
    paquete = traza_demo() if demo else traza_config(config, fecha)
    texto = json.dumps(paquete, ensure_ascii=False, default=str, indent=None if salida.endswith(".js") else 1)
    with open(salida, "w", encoding="utf-8") as fh:
        if salida.endswith(".js"):
            fh.write("// Generado con: agentes-conta traza --demo -o traza_demo.js\nwindow.TRAZA_DEMO = " + texto + ";\n")
        else:
            fh.write(texto)
    return len(paquete["eventos"])
