"""Modelo de dominio contable compartido por todos los agentes.

Todos los importes se manejan con ``Decimal`` para evitar errores de redondeo.
"""
from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

CENT = Decimal("0.01")


def dinero(valor: Any) -> Decimal:
    """Convierte cualquier valor a Decimal redondeado a céntimos."""
    if isinstance(valor, Decimal):
        d = valor
    else:
        d = Decimal(str(valor).replace(",", "."))
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def nuevo_id(prefijo: str) -> str:
    return f"{prefijo}_{uuid.uuid4().hex[:12]}"


class TipoFactura(str, Enum):
    """Tipos de factura según VeriFactu (L2 del anexo de la Orden HAC/1177/2024)."""

    F1 = "F1"  # Factura completa
    F2 = "F2"  # Factura simplificada (ticket)
    F3 = "F3"  # Factura emitida en sustitución de simplificadas
    R1 = "R1"  # Rectificativa (art. 80.1, 80.2 y error fundado en derecho)
    R2 = "R2"  # Rectificativa (art. 80.3)
    R3 = "R3"  # Rectificativa (art. 80.4)
    R4 = "R4"  # Rectificativa (resto)
    R5 = "R5"  # Rectificativa de simplificadas


class Direccion(str, Enum):
    EMITIDA = "emitida"    # venta: la emite el negocio
    RECIBIDA = "recibida"  # compra/gasto: la emite un proveedor


class EstadoFactura(str, Enum):
    BORRADOR = "borrador"
    EMITIDA = "emitida"          # registrada en el sistema (VeriFactu)
    ENVIADA = "enviada"          # enviada al cliente
    RECIBIDA = "recibida"        # factura de proveedor registrada
    PAGADA = "pagada"            # cobrada (emitida) o pagada (recibida)
    ANULADA = "anulada"


@dataclass
class Tercero:
    """Cliente o proveedor."""

    nif: str
    nombre: str
    email: Optional[str] = None
    es_proveedor: bool = False
    es_cliente: bool = False
    # Palabras que aparecen en el concepto bancario y permiten identificarlo.
    alias_bancarios: List[str] = field(default_factory=list)
    # Si emite facturas periódicas (alquiler, luz, software...).
    recurrente: bool = False
    id: str = field(default_factory=lambda: nuevo_id("ter"))


@dataclass
class LineaFactura:
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    tipo_iva: Decimal = Decimal("21")

    @property
    def base(self) -> Decimal:
        return dinero(Decimal(self.cantidad) * Decimal(self.precio_unitario))

    @property
    def cuota(self) -> Decimal:
        return dinero(self.base * Decimal(self.tipo_iva) / Decimal(100))


@dataclass
class Factura:
    numero: str
    serie: str
    fecha: date
    direccion: Direccion
    emisor_nif: str
    emisor_nombre: str
    receptor_nif: Optional[str]
    receptor_nombre: Optional[str]
    lineas: List[LineaFactura] = field(default_factory=list)
    tipo: TipoFactura = TipoFactura.F1
    estado: EstadoFactura = EstadoFactura.BORRADOR
    vencimiento: Optional[date] = None
    origen: Optional[str] = None  # ruta/ID del documento original
    # Totales declarados en el documento (si viene de un PDF de proveedor).
    base_declarada: Optional[Decimal] = None
    cuota_declarada: Optional[Decimal] = None
    total_declarado: Optional[Decimal] = None
    id: str = field(default_factory=lambda: nuevo_id("fac"))

    @property
    def num_serie(self) -> str:
        """NumSerieFactura tal y como se registra en VeriFactu."""
        return f"{self.serie}{self.numero}" if self.serie else self.numero

    @property
    def base_imponible(self) -> Decimal:
        if self.lineas:
            return dinero(sum((l.base for l in self.lineas), Decimal(0)))
        return dinero(self.base_declarada or 0)

    @property
    def cuota_total(self) -> Decimal:
        if self.lineas:
            return dinero(sum((l.cuota for l in self.lineas), Decimal(0)))
        return dinero(self.cuota_declarada or 0)

    @property
    def importe_total(self) -> Decimal:
        if self.lineas:
            return dinero(self.base_imponible + self.cuota_total)
        return dinero(self.total_declarado or (self.base_imponible + self.cuota_total))

    def desglose_iva(self) -> Dict[Decimal, Dict[str, Decimal]]:
        """Base y cuota agrupadas por tipo impositivo."""
        out: Dict[Decimal, Dict[str, Decimal]] = {}
        for l in self.lineas:
            t = Decimal(l.tipo_iva)
            acc = out.setdefault(t, {"base": Decimal(0), "cuota": Decimal(0)})
            acc["base"] += l.base
            acc["cuota"] += l.cuota
        return out


@dataclass
class MovimientoBancario:
    fecha: date
    concepto: str
    importe: Decimal  # negativo = cargo (pago), positivo = abono (cobro)
    cuenta: str = "principal"
    factura_id: Optional[str] = None  # conciliado con...
    id: str = field(default_factory=lambda: nuevo_id("mov"))

    @property
    def es_cargo(self) -> bool:
        return self.importe < 0


class EstadoFaltante(str, Enum):
    DETECTADA = "detectada"
    RECLAMADA = "reclamada"
    ESCALADA = "escalada"      # demasiados intentos: requiere intervención humana
    RESUELTA = "resuelta"


@dataclass
class FacturaFaltante:
    """Factura que debería existir pero no se ha recibido."""

    motivo: str
    proveedor_nif: Optional[str]
    proveedor_nombre: str
    importe_estimado: Optional[Decimal] = None
    periodo: Optional[str] = None  # p.ej. "2026-10"
    movimiento_id: Optional[str] = None
    estado: EstadoFaltante = EstadoFaltante.DETECTADA
    intentos: int = 0
    ultima_reclamacion: Optional[datetime] = None
    detectada_en: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: nuevo_id("fal"))


class Severidad(str, Enum):
    INFO = "info"
    AVISO = "aviso"
    ERROR = "error"


@dataclass
class Incidencia:
    """Problema detectado por el agente revisor o cualquier otro."""

    codigo: str
    mensaje: str
    severidad: Severidad = Severidad.AVISO
    referencia: Optional[str] = None
    agente: Optional[str] = None
    resuelta: bool = False
    creada_en: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=lambda: nuevo_id("inc"))


@dataclass
class EmailSaliente:
    para: str
    asunto: str
    cuerpo: str
    adjuntos: List[str] = field(default_factory=list)
    referencia: Optional[str] = None
    enviado_en: Optional[datetime] = None
    id: str = field(default_factory=lambda: nuevo_id("eml"))


def a_dict(obj: Any) -> Dict[str, Any]:
    """Serializa dataclasses a tipos JSON (Decimal→str, fechas→ISO, Enum→valor)."""

    def conv(v: Any) -> Any:
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, (date, datetime)):
            return v.isoformat()
        if isinstance(v, Enum):
            return v.value
        if isinstance(v, dict):
            return {str(conv(k)): conv(x) for k, x in v.items()}
        if isinstance(v, list):
            return [conv(x) for x in v]
        return v

    return conv(asdict(obj))
