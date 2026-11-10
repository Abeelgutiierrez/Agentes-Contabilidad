"""Interfaces de los conectores.

Los agentes dependen solo de estas interfaces. Para integrar un sistema nuevo
(Google Drive, OneDrive, Dropbox, Gmail, Outlook, un banco vía PSD2, un ERP...)
basta con implementar la interfaz correspondiente y registrarlo en la config.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Protocol, runtime_checkable

from ..models import EmailSaliente, MovimientoBancario


@dataclass
class Documento:
    id: str
    nombre: str
    texto: str  # contenido textual (texto plano, JSON o texto extraído del PDF)
    origen: str  # nombre del conector
    metadatos: Dict[str, str] = field(default_factory=dict)


@runtime_checkable
class FuenteDocumentos(Protocol):
    """Lugar de donde llegan facturas de proveedores (carpeta, Drive, email...)."""

    nombre: str

    def nuevos_documentos(self) -> List[Documento]: ...


@runtime_checkable
class Correo(Protocol):
    def enviar(self, email: EmailSaliente) -> None: ...


@runtime_checkable
class FuenteBancaria(Protocol):
    def movimientos(self) -> List[MovimientoBancario]: ...


@dataclass
class RespuestaAEAT:
    aceptados: List[int]
    rechazados: Dict[int, str]
    csv: Optional[str] = None  # Código Seguro de Verificación del envío


@runtime_checkable
class ClienteAEAT(Protocol):
    def enviar_registros(self, sobre_xml: str, secuencias: List[int]) -> RespuestaAEAT: ...
