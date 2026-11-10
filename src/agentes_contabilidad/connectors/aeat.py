"""Clientes para remitir registros VeriFactu a la AEAT.

``AEATSimulado`` acepta todo (desarrollo y tests). ``AEATSoap`` es el esqueleto
del cliente real: requiere certificado electrónico (persona física, jurídica
o de representante) y debe probarse primero en el entorno de pruebas.
"""
from __future__ import annotations

import uuid
from typing import List

from .base import RespuestaAEAT

ENDPOINTS = {
    "pruebas": "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
    "produccion": "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
}


class AEATSimulado:
    def __init__(self) -> None:
        self.recibidos: List[str] = []

    def enviar_registros(self, sobre_xml: str, secuencias: List[int]) -> RespuestaAEAT:
        self.recibidos.append(sobre_xml)
        return RespuestaAEAT(aceptados=list(secuencias), rechazados={}, csv=f"SIM-{uuid.uuid4().hex[:16].upper()}")


class AEATSoap:
    """Cliente SOAP con certificado. Pendiente de validar contra el entorno de pruebas."""

    def __init__(self, cert_pem: str, key_pem: str, entorno: str = "pruebas") -> None:
        self.cert = (cert_pem, key_pem)
        self.url = ENDPOINTS[entorno]

    def enviar_registros(self, sobre_xml: str, secuencias: List[int]) -> RespuestaAEAT:
        import requests  # type: ignore

        envelope = (
            '<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">'
            f"<soapenv:Header/><soapenv:Body>{sobre_xml}</soapenv:Body></soapenv:Envelope>"
        )
        r = requests.post(self.url, data=envelope.encode("utf-8"), cert=self.cert,
                          headers={"Content-Type": "text/xml; charset=utf-8"}, timeout=60)
        r.raise_for_status()
        # TODO: parsear RespuestaRegFactuSistemaFacturacion (EstadoEnvio,
        # RespuestaLinea por registro, CSV) y mapear a aceptados/rechazados.
        raise NotImplementedError("Parseo de la respuesta de la AEAT pendiente de implementar: " + r.text[:300])
