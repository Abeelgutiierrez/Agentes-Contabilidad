"""Validaciones fiscales españolas: NIF/NIE/CIF y tipos de IVA."""
from __future__ import annotations

import re
from decimal import Decimal

LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"
TIPOS_IVA_VALIDOS = {Decimal(x) for x in ("0", "4", "5", "10", "21")}
# Recargo de equivalencia
TIPOS_RE = {Decimal(x) for x in ("0.5", "0.62", "1.4", "1.75", "5.2")}


def normalizar_nif(nif: str) -> str:
    return re.sub(r"[\s\-\.]", "", (nif or "").upper())


def validar_nif(nif: str) -> bool:
    """Valida DNI, NIE o CIF (NIF de persona jurídica) españoles."""
    n = normalizar_nif(nif)
    if n.startswith("ES"):
        n = n[2:]
    if re.fullmatch(r"\d{8}[A-Z]", n):
        return LETRAS_DNI[int(n[:8]) % 23] == n[8]
    if re.fullmatch(r"[XYZ]\d{7}[A-Z]", n):
        num = str("XYZ".index(n[0])) + n[1:8]
        return LETRAS_DNI[int(num) % 23] == n[8]
    if re.fullmatch(r"[KLM]\d{7}[A-Z]", n):  # NIF especiales de personas físicas
        return LETRAS_DNI[int(n[1:8]) % 23] == n[8]
    if re.fullmatch(r"[ABCDEFGHJNPQRSUVW]\d{7}[0-9A-J]", n):
        return _validar_cif(n)
    return False


def _validar_cif(n: str) -> bool:
    digitos = n[1:8]
    pares = sum(int(digitos[i]) for i in range(1, 7, 2))
    impares = 0
    for i in range(0, 7, 2):
        d = int(digitos[i]) * 2
        impares += d // 10 + d % 10
    control = (10 - (pares + impares) % 10) % 10
    letra = "JABCDEFGHI"[control]
    c = n[8]
    if n[0] in "PQRSNW":  # siempre letra
        return c == letra
    if n[0] in "ABEH":  # siempre número
        return c == str(control)
    return c in (str(control), letra)


def tipo_iva_valido(tipo: Decimal) -> bool:
    return Decimal(tipo) in TIPOS_IVA_VALIDOS
