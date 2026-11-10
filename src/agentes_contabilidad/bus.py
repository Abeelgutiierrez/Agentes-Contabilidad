"""Bus de mensajes entre agentes (publicar/suscribir).

Los agentes no se llaman directamente entre sí: publican eventos en el bus y
otros agentes suscritos reaccionan. Así se pueden añadir, quitar o sustituir
agentes sin tocar el resto del ecosistema.

El bus es síncrono y en proceso (suficiente para un pequeño negocio). La
interfaz está pensada para poder cambiarlo por Redis/NATS/colas en la nube sin
modificar los agentes.
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Deque, Dict, List

log = logging.getLogger(__name__)


class Temas:
    """Catálogo de eventos del ecosistema (contrato entre agentes)."""

    CICLO_INICIADO = "ciclo.iniciado"
    DOCUMENTO_RECIBIDO = "documento.recibido"          # {ruta, contenido, origen}
    FACTURA_RECIBIDA = "factura.recibida"              # {factura}
    FACTURA_A_EMITIR = "factura.a_emitir"              # {factura}
    FACTURA_EMITIDA = "factura.emitida"                # {factura, registro}
    FACTURA_ENVIADA = "factura.enviada"                # {factura, email}
    RECORDATORIO_COBRO = "cobro.recordatorio"          # {factura, email}
    AEAT_ENVIO = "aeat.envio"                          # {aceptados, rechazados, csv}
    MOVIMIENTO_BANCARIO = "banco.movimiento"           # {movimiento}
    MOVIMIENTO_CONCILIADO = "banco.conciliado"         # {movimiento, factura}
    FACTURA_FALTANTE = "factura.faltante"              # {faltante}
    FACTURA_FALTANTE_RESUELTA = "factura.faltante_resuelta"
    RECLAMACION_ENVIADA = "reclamacion.enviada"        # {faltante, email}
    ESCALADO_HUMANO = "escalado.humano"                # {motivo, referencia}
    INCIDENCIA = "revision.incidencia"                 # {incidencia}
    INCIDENCIA_RESUELTA = "revision.resuelta"          # {incidencia}
    REVISION_SOLICITADA = "revision.solicitada"
    INFORME_FISCAL = "fiscal.informe"                  # {informe}
    CICLO_TERMINADO = "ciclo.terminado"


@dataclass
class Mensaje:
    tema: str
    datos: Dict[str, Any]
    emisor: str
    momento: datetime = field(default_factory=datetime.now)


Manejador = Callable[[Mensaje], None]


class Bus:
    def __init__(self) -> None:
        self._subs: Dict[str, List[Manejador]] = defaultdict(list)
        self._nombres: Dict[str, List[str]] = defaultdict(list)  # quién escucha cada tema
        self._cola: Deque[Mensaje] = deque()
        self._despachando = False
        self.historial: List[Mensaje] = []

    def suscribir(self, tema: str, manejador: Manejador, nombre: str | None = None) -> None:
        """Suscribe a un tema. ``*`` recibe todos los mensajes.

        ``nombre`` identifica al suscriptor (p.ej. el agente) para poder
        dibujar quién recibe cada mensaje en el panel visual.
        """
        self._subs[tema].append(manejador)
        if nombre and nombre not in self._nombres[tema]:
            self._nombres[tema].append(nombre)

    def destinatarios(self, tema: str) -> List[str]:
        return list(self._nombres.get(tema, []))

    def publicar(self, tema: str, datos: Dict[str, Any] | None = None, emisor: str = "sistema") -> None:
        msg = Mensaje(tema=tema, datos=datos or {}, emisor=emisor)
        self._cola.append(msg)
        # Despacho en anchura: un agente que publica dentro de un manejador no
        # provoca recursión profunda; el mensaje se procesa al terminar el actual.
        if not self._despachando:
            self._despachar()

    def _despachar(self) -> None:
        self._despachando = True
        try:
            while self._cola:
                msg = self._cola.popleft()
                self.historial.append(msg)
                log.debug("[%s] %s -> %s", msg.emisor, msg.tema, list(msg.datos))
                for h in list(self._subs.get(msg.tema, [])) + list(self._subs.get("*", [])):
                    try:
                        h(msg)
                    except Exception:  # un agente que falla no tumba el ecosistema
                        log.exception("Error manejando %s en %s", msg.tema, h)
        finally:
            self._despachando = False

    def contar(self, tema: str) -> int:
        return sum(1 for m in self.historial if m.tema == tema)
