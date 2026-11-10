"""Agente Fiscal: prepara la información para la asesoría y los modelos de IVA."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Dict, List

from ..bus import Temas
from ..models import Direccion, EstadoFactura, dinero
from .base import Agente

# Plazos del modelo 303 (régimen general trimestral)
PLAZOS_303 = {1: (4, 20), 2: (7, 20), 3: (10, 20), 4: (1, 30)}


def trimestre_de(d: date) -> int:
    return (d.month - 1) // 3 + 1


def plazo_303(anio: int, trimestre: int) -> date:
    mes, dia = PLAZOS_303[trimestre]
    return date(anio + 1 if trimestre == 4 else anio, mes, dia)


@dataclass
class InformeFiscal:
    anio: int
    trimestre: int
    repercutido: Dict[str, Dict[str, str]] = field(default_factory=dict)
    soportado: Dict[str, Dict[str, str]] = field(default_factory=dict)
    total_repercutido: Decimal = Decimal(0)
    total_soportado: Decimal = Decimal(0)
    resultado_303: Decimal = Decimal(0)
    plazo: date = date.today()
    avisos: List[str] = field(default_factory=list)

    def texto(self) -> str:
        r = [f"Modelo 303 (borrador) — {self.trimestre}T {self.anio}",
             f"  IVA repercutido: {self.total_repercutido} €",
             f"  IVA soportado deducible: {self.total_soportado} €",
             f"  Resultado: {self.resultado_303} € ({'a ingresar' if self.resultado_303 > 0 else 'a compensar/devolver'})",
             f"  Plazo de presentación: {self.plazo:%d/%m/%Y}"]
        r += [f"  ⚠ {a}" for a in self.avisos]
        return "\n".join(r)


class AgenteFiscal(Agente):
    nombre = "fiscal"
    rol = "Calcula el IVA trimestral (303), vigila plazos y prepara el paquete para la asesoría."
    fases = ("informe",)

    def informe(self, anio: int, trimestre: int) -> InformeFiscal:
        inf = InformeFiscal(anio=anio, trimestre=trimestre, plazo=plazo_303(anio, trimestre))
        for direccion, destino in ((Direccion.EMITIDA, inf.repercutido), (Direccion.RECIBIDA, inf.soportado)):
            acc: Dict[Decimal, Dict[str, Decimal]] = {}
            for f in self.libro.facturas_de(direccion):
                if f.estado in (EstadoFactura.ANULADA, EstadoFactura.BORRADOR):
                    continue
                if f.fecha.year != anio or trimestre_de(f.fecha) != trimestre:
                    continue
                if direccion == Direccion.RECIBIDA and not f.lineas:
                    acc.setdefault(Decimal(-1), {"base": Decimal(0), "cuota": Decimal(0)})
                    acc[Decimal(-1)]["base"] += f.base_imponible
                    acc[Decimal(-1)]["cuota"] += f.cuota_total
                    continue
                for tipo, v in f.desglose_iva().items():
                    a = acc.setdefault(tipo, {"base": Decimal(0), "cuota": Decimal(0)})
                    a["base"] += v["base"]
                    a["cuota"] += v["cuota"]
            for tipo, v in acc.items():
                clave = "sin desglose" if tipo < 0 else f"{tipo}%"
                destino[clave] = {"base": str(dinero(v["base"])), "cuota": str(dinero(v["cuota"]))}
        inf.total_repercutido = dinero(sum((Decimal(v["cuota"]) for v in inf.repercutido.values()), Decimal(0)))
        inf.total_soportado = dinero(sum((Decimal(v["cuota"]) for v in inf.soportado.values()), Decimal(0)))
        inf.resultado_303 = dinero(inf.total_repercutido - inf.total_soportado)
        faltan = self.libro.faltantes_abiertas()
        if faltan:
            inf.avisos.append(f"{len(faltan)} facturas de proveedor pendientes: el IVA soportado puede estar infravalorado")
        abiertas = [i for i in self.libro.incidencias.values() if not i.resuelta and i.severidad.value == "error"]
        if abiertas:
            inf.avisos.append(f"{len(abiertas)} incidencias graves sin resolver")
        dias = (inf.plazo - self.ctx.hoy).days
        if 0 <= dias <= 15:
            inf.avisos.append(f"Quedan {dias} días para presentar el modelo 303")
        return inf

    def ejecutar_fase(self, fase: str) -> None:
        hoy = self.ctx.hoy
        inf = self.informe(hoy.year, trimestre_de(hoy))
        self.publicar(Temas.INFORME_FISCAL, informe=inf)
