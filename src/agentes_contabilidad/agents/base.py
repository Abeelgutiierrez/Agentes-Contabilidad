"""Clase base de todos los agentes del ecosistema."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional

from ..bus import Bus, Mensaje, Temas
from ..connectors.base import ClienteAEAT, Correo, FuenteBancaria, FuenteDocumentos
from ..libro import Libro
from ..llm import LLM
from ..models import Incidencia, Severidad
from ..verifactu.registro import SistemaVeriFactu


@dataclass
class Politicas:
    """Parámetros de negocio que gobiernan a los agentes (configurables)."""

    dias_gracia_factura: int = 5           # días tras un pago antes de considerar que falta factura
    dias_entre_reclamaciones: int = 7
    max_reclamaciones: int = 3             # después se escala a una persona
    dias_vencimiento: int = 30             # vencimiento por defecto de facturas emitidas
    dias_entre_recordatorios_cobro: int = 7
    tolerancia_conciliacion: str = "0.01"
    ventana_conciliacion_dias: int = 60
    serie_por_defecto: str = "A"
    # Conceptos bancarios que nunca llevan factura de proveedor
    conceptos_sin_factura: List[str] = field(default_factory=lambda: [
        "NOMINA", "TGSS", "SEGURIDAD SOCIAL", "AEAT", "AGENCIA TRIBUTARIA", "IMPUESTO",
        "COMISION", "TRASPASO", "TRANSFERENCIA INTERNA", "PRESTAMO", "INTERESES",
    ])


@dataclass
class Contexto:
    """Todo lo que un agente puede necesitar: estado, conectores e IA."""

    bus: Bus
    libro: Libro
    verifactu: SistemaVeriFactu
    llm: LLM
    politicas: Politicas = field(default_factory=Politicas)
    fuentes_documentos: List[FuenteDocumentos] = field(default_factory=list)
    banco: List[FuenteBancaria] = field(default_factory=list)
    correo: Optional[Correo] = None
    aeat: Optional[ClienteAEAT] = None
    hoy: date = field(default_factory=date.today)


class Agente:
    """Un agente tiene un rol, se suscribe a temas del bus y publica resultados."""

    nombre: str = "agente"
    rol: str = ""
    # Fases del ciclo diario en las que participa (ver Orquestador.FASES)
    fases: tuple = ()

    def __init__(self, ctx: Contexto) -> None:
        self.ctx = ctx
        self.log = logging.getLogger(f"agente.{self.nombre}")
        for fase in self.fases:
            ctx.bus.suscribir(f"fase.{fase}", self._en_fase)
        self.suscribir()

    # --- a sobreescribir por cada agente
    def suscribir(self) -> None:
        """Registra manejadores reactivos (eventos de otros agentes)."""

    def ejecutar_fase(self, fase: str) -> None:
        """Trabajo programado dentro del ciclo."""

    # --- utilidades
    def _en_fase(self, msg: Mensaje) -> None:
        self.ejecutar_fase(msg.datos["fase"])

    @property
    def libro(self) -> Libro:
        return self.ctx.libro

    def publicar(self, tema: str, **datos: Any) -> None:
        self.ctx.bus.publicar(tema, datos, emisor=self.nombre)

    def escuchar(self, tema: str, manejador) -> None:
        self.ctx.bus.suscribir(tema, manejador)

    def incidencia(self, codigo: str, mensaje: str, severidad: Severidad = Severidad.AVISO,
                   referencia: Optional[str] = None) -> Incidencia:
        # Evita duplicar la misma incidencia abierta
        for i in self.libro.incidencias.values():
            if not i.resuelta and i.codigo == codigo and i.referencia == referencia:
                return i
        inc = Incidencia(codigo=codigo, mensaje=mensaje, severidad=severidad,
                         referencia=referencia, agente=self.nombre)
        self.libro.incidencias[inc.id] = inc
        self.publicar(Temas.INCIDENCIA, incidencia=inc)
        self.log.info("Incidencia %s: %s", codigo, mensaje)
        return inc

    def describir(self) -> Dict[str, Any]:
        return {"nombre": self.nombre, "rol": self.rol, "fases": list(self.fases)}
