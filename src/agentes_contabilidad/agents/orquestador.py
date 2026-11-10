"""Orquestador: monta el ecosistema y dirige el ciclo de trabajo diario."""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Type

from ..bus import Mensaje, Temas
from ..models import Factura, Severidad
from .base import Agente, Contexto
from .cobros import AgenteCobros
from .conciliador import AgenteConciliador
from .emisor import AgenteEmisor
from .facturas_faltantes import AgenteFacturasFaltantes
from .fiscal import AgenteFiscal, InformeFiscal
from .reclamador import AgenteReclamador
from .recepcion import AgenteRecepcion
from .revisor import AgenteRevisor

AGENTES_POR_DEFECTO: List[Type[Agente]] = [
    AgenteRecepcion,
    AgenteConciliador,
    AgenteFacturasFaltantes,
    AgenteReclamador,
    AgenteEmisor,
    AgenteCobros,
    AgenteRevisor,
    AgenteFiscal,
]

PROMPT_ASISTENTE = """Eres el director de un equipo de agentes contables que lleva la
contabilidad de un pequeño negocio español (VeriFactu, IVA, facturas). Respondes al
dueño del negocio de forma clara y breve usando SOLO los datos del estado que se te
proporciona. Si algo requiere a un asesor fiscal humano, dilo."""


class Orquestador:
    # Orden de las fases de un ciclo. Cada agente declara en cuáles participa.
    FASES = ("ingesta", "banco", "deteccion", "reclamaciones", "cobros", "envio_aeat", "revision", "informe")

    def __init__(self, ctx: Contexto, agentes: Optional[List[Type[Agente]]] = None) -> None:
        self.ctx = ctx
        self.agentes: Dict[str, Agente] = {}
        for cls in agentes or AGENTES_POR_DEFECTO:
            a = cls(ctx)
            self.agentes[a.nombre] = a
        self.ultimo_informe: Optional[InformeFiscal] = None
        self.ruta_libro: Optional[str] = None  # si se fija, el estado se guarda tras cada ciclo
        ctx.bus.suscribir(Temas.INFORME_FISCAL, self._on_informe)

    def _on_informe(self, msg: Mensaje) -> None:
        self.ultimo_informe = msg.datos["informe"]

    def agente(self, nombre: str) -> Agente:
        return self.agentes[nombre]

    # ---------------------------------------------------------- acciones
    def ciclo(self, hoy: Optional[date] = None) -> Dict[str, int]:
        """Ejecuta un ciclo completo (pensado para lanzarse a diario)."""
        if hoy:
            self.ctx.hoy = hoy
        bus = self.ctx.bus
        bus.publicar(Temas.CICLO_INICIADO, {"hoy": self.ctx.hoy}, emisor="orquestador")
        for fase in self.FASES:
            bus.publicar(f"fase.{fase}", {"fase": fase}, emisor="orquestador")
        resumen = self.ctx.libro.resumen()
        bus.publicar(Temas.CICLO_TERMINADO, {"resumen": resumen}, emisor="orquestador")
        self.guardar()
        return resumen

    def guardar(self) -> None:
        if self.ruta_libro:
            self.ctx.libro.guardar(self.ruta_libro)

    def emitir_factura(self, factura: Factura) -> bool:
        """Punto de entrada para que el negocio (o un TPV/ERP) emita una venta."""
        n = len(self.ctx.libro.facturas)
        self.ctx.bus.publicar(Temas.FACTURA_A_EMITIR, {"factura": factura}, emisor="orquestador")
        self.guardar()
        return len(self.ctx.libro.facturas) > n and factura.estado.value != "borrador"

    # ---------------------------------------------------------- informes
    def panel(self) -> str:
        lb = self.ctx.libro
        lineas = [f"=== {lb.nombre_empresa} ({lb.nif_empresa}) — {self.ctx.hoy:%d/%m/%Y} ==="]
        for k, v in lb.resumen().items():
            lineas.append(f"  {k.replace('_', ' ')}: {v}")
        faltan = lb.faltantes_abiertas()
        if faltan:
            lineas.append("\nFacturas que faltan:")
            for f in faltan:
                lineas.append(f"  [{f.estado.value}] {f.proveedor_nombre}: {f.motivo} (reclamaciones: {f.intentos})")
        inc = [i for i in lb.incidencias.values() if not i.resuelta]
        if inc:
            lineas.append("\nIncidencias abiertas:")
            orden = {Severidad.ERROR: 0, Severidad.AVISO: 1, Severidad.INFO: 2}
            for i in sorted(inc, key=lambda x: orden[x.severidad]):
                lineas.append(f"  [{i.severidad.value}] ({i.agente}) {i.mensaje}")
        cadena = self.ctx.verifactu.verificar_cadena()
        n = len(self.ctx.verifactu.registros())
        lineas.append(f"\nVeriFactu: {n} registros, cadena {'ÍNTEGRA' if not cadena else 'ROTA'}")
        if self.ultimo_informe:
            lineas.append("\n" + self.ultimo_informe.texto())
        return "\n".join(lineas)

    def preguntar(self, pregunta: str) -> str:
        """Pregunta en lenguaje natural sobre el estado de la contabilidad."""
        estado = self.panel()
        if not self.ctx.llm.disponible:
            return "(Modo sin IA: configura ANTHROPIC_API_KEY para hacer preguntas.)\n\n" + estado
        return self.ctx.llm.completar(PROMPT_ASISTENTE, f"ESTADO:\n{estado}\n\nPREGUNTA: {pregunta}") or estado

    def describir(self) -> List[dict]:
        return [a.describir() for a in self.agentes.values()]
