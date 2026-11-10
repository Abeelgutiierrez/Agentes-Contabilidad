"""Construcción del ecosistema a partir de un fichero de configuración JSON."""
from __future__ import annotations

import json
import os
from dataclasses import fields
from decimal import Decimal
from typing import Any, Dict

from .agents.base import Contexto, Politicas
from .agents.orquestador import Orquestador
from .bus import Bus
from .connectors import (
    AEATSimulado,
    AEATSoap,
    BancoCSV,
    BuzonIMAP,
    CarpetaLocal,
    CorreoSimulado,
    CorreoSMTP,
    GoogleDrive,
)
from .libro import Libro
from .llm import LLM
from .models import Tercero
from .verifactu.registro import SistemaVeriFactu


def _ruta(base: str, p: str) -> str:
    return p if os.path.isabs(p) else os.path.normpath(os.path.join(base, p))


def _env(v: Any) -> Any:
    """Permite valores "$VARIABLE" para no guardar secretos en el JSON."""
    if isinstance(v, str) and v.startswith("$"):
        return os.getenv(v[1:], "")
    return v


def crear_documentos(c: Dict[str, Any], base: str):
    tipo = c["tipo"]
    if tipo == "carpeta":
        return CarpetaLocal(_ruta(base, c["ruta"]), c.get("nombre", "carpeta_local"))
    if tipo == "google_drive":
        return GoogleDrive(c["carpeta_id"], _env(c.get("credenciales")))
    if tipo == "imap":
        return BuzonIMAP(c["servidor"], _env(c["usuario"]), _env(c["clave"]), c.get("carpeta", "INBOX"))
    raise ValueError(f"Conector de documentos desconocido: {tipo}")


def crear_ecosistema(ruta_config: str) -> Orquestador:
    with open(ruta_config, encoding="utf-8") as fh:
        cfg = json.load(fh)
    base = os.path.dirname(os.path.abspath(ruta_config))
    emp = cfg["empresa"]
    datos = _ruta(base, cfg.get("carpeta_datos", "./datos_runtime"))
    os.makedirs(datos, exist_ok=True)
    ruta_libro = os.path.join(datos, "libro.pkl")
    if os.path.exists(ruta_libro):
        libro = Libro.cargar(ruta_libro)
    else:
        libro = Libro(emp["nif"], emp["nombre"], emp.get("email", ""))
    for t in cfg.get("terceros", []):
        libro.alta_tercero(Tercero(**t))
    vf = SistemaVeriFactu(os.path.join(datos, "verifactu.sqlite"), entorno=cfg.get("entorno_verifactu", "pruebas"))

    validos = {f.name for f in fields(Politicas)}
    politicas = Politicas(**{k: v for k, v in cfg.get("politicas", {}).items() if k in validos})

    con = cfg.get("conectores", {})
    correo_cfg = con.get("correo", {"tipo": "simulado"})
    if correo_cfg["tipo"] == "smtp":
        correo = CorreoSMTP(correo_cfg["servidor"], int(correo_cfg.get("puerto", 587)), _env(correo_cfg["usuario"]),
                            _env(correo_cfg["clave"]), correo_cfg.get("remitente", emp.get("email", "")))
    else:
        correo = CorreoSimulado(_ruta(base, correo_cfg.get("carpeta", os.path.join(datos, "bandeja_salida"))))

    aeat_cfg = con.get("aeat", {"tipo": "simulado"})
    aeat = (AEATSoap(_env(aeat_cfg["cert"]), _env(aeat_cfg["key"]), cfg.get("entorno_verifactu", "pruebas"))
            if aeat_cfg["tipo"] == "soap" else AEATSimulado())

    ctx = Contexto(
        bus=Bus(), libro=libro, verifactu=vf, llm=LLM(), politicas=politicas,
        fuentes_documentos=[crear_documentos(c, base) for c in con.get("documentos", [])],
        banco=[BancoCSV(_ruta(base, b["ruta"]), b.get("cuenta", "principal")) for b in con.get("banco", [])],
        correo=correo, aeat=aeat,
    )
    orq = Orquestador(ctx)
    orq.ruta_libro = ruta_libro
    return orq
