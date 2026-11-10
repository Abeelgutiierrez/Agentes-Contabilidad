"""Agente Recepcionista: convierte documentos entrantes en facturas recibidas."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, Optional

from ..bus import Mensaje, Temas
from ..connectors.base import Documento
from ..models import (
    Direccion,
    EstadoFactura,
    Factura,
    LineaFactura,
    Severidad,
    Tercero,
    TipoFactura,
    dinero,
)
from ..verifactu.validaciones import normalizar_nif
from .base import Agente

PROMPT_EXTRACCION = """Eres un experto contable español. Extrae los datos de la factura del texto.
Devuelve JSON con: numero, serie (puede ser ""), fecha (AAAA-MM-DD), vencimiento (o null),
emisor {nif, nombre, email}, receptor {nif, nombre}, base_imponible, cuota_iva, total,
lineas [{descripcion, cantidad, precio_unitario, tipo_iva}]. Si el documento NO es una
factura devuelve {"es_factura": false}."""

RE_NIF = r"([A-Z]\d{7}[0-9A-J]|\d{8}[A-Z]|[XYZ]\d{7}[A-Z])"


def _num(txt: str) -> Decimal:
    t = txt.strip().replace("€", "").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    return dinero(t.replace(",", "."))


def _fecha(txt: Optional[str]) -> Optional[date]:
    if not txt:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(txt.strip(), fmt).date()
        except ValueError:
            pass
    return None


class AgenteRecepcion(Agente):
    nombre = "recepcion"
    rol = "Lee los documentos que llegan (carpetas, Drive, email) y registra las facturas de proveedores."
    fases = ("ingesta",)

    def suscribir(self) -> None:
        self.escuchar(Temas.DOCUMENTO_RECIBIDO, self._on_documento)

    def ejecutar_fase(self, fase: str) -> None:
        for fuente in self.ctx.fuentes_documentos:
            try:
                for doc in fuente.nuevos_documentos():
                    if doc.id in self.libro.documentos_vistos:
                        continue
                    self.libro.documentos_vistos.add(doc.id)
                    self.publicar(Temas.DOCUMENTO_RECIBIDO, documento=doc)
            except Exception as e:  # conector caído: se avisa, el resto sigue
                self.incidencia("CONECTOR_ERROR", f"Error leyendo {getattr(fuente, 'nombre', fuente)}: {e}",
                                Severidad.ERROR, getattr(fuente, "nombre", None))

    # ---------------------------------------------------------------- core
    def _on_documento(self, msg: Mensaje) -> None:
        doc: Documento = msg.datos["documento"]
        datos = self.extraer(doc.texto)
        if not datos or datos.get("es_factura") is False:
            self.incidencia("DOC_NO_RECONOCIDO", f"No se reconoce como factura: {doc.nombre}",
                            Severidad.INFO, doc.id)
            return
        factura = self._a_factura(datos, doc)
        if factura is None:
            self.incidencia("DOC_INCOMPLETO", f"Faltan datos obligatorios en {doc.nombre}", Severidad.AVISO, doc.id)
            return
        if self.libro.buscar_factura(factura.emisor_nif, factura.num_serie):
            self.incidencia("FACTURA_DUPLICADA",
                            f"Factura {factura.num_serie} de {factura.emisor_nombre} ya registrada ({doc.nombre})",
                            Severidad.AVISO, doc.id)
            return
        self.libro.anadir_factura(factura)
        self.log.info("Factura recibida %s de %s (%s €)", factura.num_serie, factura.emisor_nombre, factura.importe_total)
        self.publicar(Temas.FACTURA_RECIBIDA, factura=factura)

    def extraer(self, texto: str) -> Optional[Dict[str, Any]]:
        """JSON estructurado → Claude → expresiones regulares (en ese orden)."""
        t = texto.strip()
        if t.startswith("{"):
            try:
                return json.loads(t)
            except json.JSONDecodeError:
                pass
        if self.ctx.llm.disponible:
            datos = self.ctx.llm.completar_json(PROMPT_EXTRACCION, texto[:15000])
            if datos:
                return datos
        return self._extraer_regex(texto)

    @staticmethod
    def _extraer_regex(texto: str) -> Optional[Dict[str, Any]]:
        if not re.search(r"factura", texto, re.I):
            return {"es_factura": False}

        def buscar(patron: str) -> Optional[str]:
            m = re.search(patron, texto, re.I | re.M)
            return m.group(1).strip() if m else None

        nifs = re.findall(RE_NIF, texto.upper())
        emisor_nif = buscar(r"NIF\s*(?:emisor|proveedor)?\s*[:\-]?\s*" + RE_NIF) or (nifs[0] if nifs else None)
        receptor_nif = buscar(r"NIF\s*(?:cliente|receptor|destinatario)\s*[:\-]?\s*" + RE_NIF)
        if not receptor_nif and len(nifs) > 1:
            receptor_nif = next((n for n in nifs if n != emisor_nif), None)
        return {
            "numero": buscar(r"(?:n[ºo°]\.?|n[úu]mero)\s*(?:de\s*)?factura\s*[:\-]?\s*([\w\-/]+)")
            or buscar(r"factura\s*(?:n[ºo°]\.?|n[úu]m\.?|n[úu]mero)?\s*[:\-]\s*([\w\-/]+)"),
            "serie": "",
            "fecha": buscar(r"fecha(?:\s*de\s*(?:emisi[óo]n|expedici[óo]n|factura))?\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2})"),
            "vencimiento": buscar(r"vencimiento\s*[:\-]?\s*(\d{1,2}[/-]\d{1,2}[/-]\d{4}|\d{4}-\d{2}-\d{2})"),
            "emisor": {"nif": emisor_nif, "nombre": buscar(r"^(?:emisor|proveedor|raz[óo]n social)\s*[:\-]\s*(.+)$"),
                       "email": buscar(r"([\w.\-+]+@[\w\-]+\.[\w.\-]+)")},
            "receptor": {"nif": receptor_nif, "nombre": buscar(r"^(?:cliente|receptor)\s*[:\-]\s*(.+)$")},
            "base_imponible": buscar(r"base\s*imponible\s*[:\-]?\s*([\d.,]+)"),
            "cuota_iva": buscar(r"(?:cuota\s*)?iva(?:\s*\(?\d+\s*%\)?)?\s*[:\-]\s*([\d.,]+)"),
            "tipo_iva": buscar(r"iva\s*\(?(\d+(?:[.,]\d+)?)\s*%"),
            "total": buscar(r"total(?:\s*factura|\s*a\s*pagar)?\s*[:\-]?\s*([\d.,]+)"),
        }

    def _a_factura(self, d: Dict[str, Any], doc: Documento) -> Optional[Factura]:
        emisor = d.get("emisor") or {}
        receptor = d.get("receptor") or {}
        fecha = _fecha(d.get("fecha"))
        if not (d.get("numero") and fecha and emisor.get("nif")):
            return None
        nif = normalizar_nif(emisor["nif"])
        tercero = self.libro.tercero_por_nif(nif)
        if tercero is None:
            tercero = self.libro.alta_tercero(Tercero(
                nif=nif, nombre=emisor.get("nombre") or nif, email=emisor.get("email"), es_proveedor=True,
            ))
        elif not tercero.email and emisor.get("email"):
            tercero.email = emisor["email"]
        lineas = [
            LineaFactura(l.get("descripcion", ""), Decimal(str(l.get("cantidad", 1))),
                         _num(str(l.get("precio_unitario", 0))), Decimal(str(l.get("tipo_iva", 21))))
            for l in d.get("lineas") or []
        ]
        f = Factura(
            numero=str(d["numero"]), serie=str(d.get("serie") or ""), fecha=fecha,
            direccion=Direccion.RECIBIDA, emisor_nif=nif, emisor_nombre=tercero.nombre,
            receptor_nif=normalizar_nif(receptor.get("nif") or "") or None,
            receptor_nombre=receptor.get("nombre"), lineas=lineas,
            tipo=TipoFactura(d.get("tipo", "F1")), estado=EstadoFactura.RECIBIDA,
            vencimiento=_fecha(d.get("vencimiento")), origen=doc.id,
            base_declarada=_num(str(d["base_imponible"])) if d.get("base_imponible") else None,
            cuota_declarada=_num(str(d["cuota_iva"])) if d.get("cuota_iva") else None,
            total_declarado=_num(str(d["total"])) if d.get("total") else None,
        )
        if not lineas and f.base_declarada is not None and d.get("tipo_iva"):
            # Guardamos el tipo para el desglose fiscal si solo vienen totales
            f.lineas = [LineaFactura("Según factura", Decimal(1), f.base_declarada, _num(str(d["tipo_iva"])))]
        return f
