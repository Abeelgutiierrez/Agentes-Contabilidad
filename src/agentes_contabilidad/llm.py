"""Acceso a Claude (API de Anthropic) con degradación elegante.

Si no hay ``ANTHROPIC_API_KEY`` o el paquete ``anthropic`` no está instalado,
los agentes funcionan igualmente con reglas y plantillas deterministas. Esto
permite ejecutar los tests y la demo sin coste ni conexión.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

MODELO_POR_DEFECTO = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5")


class LLM:
    def __init__(self, modelo: str = MODELO_POR_DEFECTO, api_key: Optional[str] = None) -> None:
        self.modelo = modelo
        self._cliente = None
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if key:
            try:
                import anthropic  # type: ignore

                self._cliente = anthropic.Anthropic(api_key=key)
            except ImportError:
                log.warning("Paquete 'anthropic' no instalado: se usará el modo sin IA")

    @property
    def disponible(self) -> bool:
        return self._cliente is not None

    def completar(self, sistema: str, usuario: str, max_tokens: int = 1024) -> Optional[str]:
        if not self._cliente:
            return None
        try:
            resp = self._cliente.messages.create(
                model=self.modelo,
                max_tokens=max_tokens,
                system=sistema,
                messages=[{"role": "user", "content": usuario}],
            )
            return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        except Exception:  # red, cuota, etc.: el agente cae a su modo determinista
            log.exception("Fallo llamando a Claude")
            return None

    def completar_json(self, sistema: str, usuario: str, max_tokens: int = 1024) -> Optional[Dict[str, Any]]:
        texto = self.completar(sistema + "\nResponde únicamente con un objeto JSON válido.", usuario, max_tokens)
        if not texto:
            return None
        m = re.search(r"\{.*\}", texto, re.S)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
