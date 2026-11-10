"""Agentes Contabilidad: ecosistema de agentes de IA para la contabilidad de pequeños negocios (VeriFactu)."""

__version__ = "0.2.0"

from .agents import Contexto, Orquestador, Politicas  # noqa: E402
from .bus import Bus, Temas  # noqa: E402
from .config import crear_ecosistema  # noqa: E402
from .libro import Libro  # noqa: E402

__all__ = ["Bus", "Temas", "Contexto", "Orquestador", "Politicas", "Libro", "crear_ecosistema", "__version__"]
