"""Fuentes de documentos: carpeta local, Google Drive y buzón IMAP."""
from __future__ import annotations

import email
import imaplib
import logging
import os
from typing import List, Optional, Set

from .base import Documento

log = logging.getLogger(__name__)
EXTENSIONES = {".txt", ".json", ".pdf", ".xml", ".md"}


def extraer_texto_pdf(ruta_o_bytes) -> str:
    """Extrae texto de un PDF si ``pypdf`` está instalado."""
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        log.warning("pypdf no instalado: no se puede leer el PDF")
        return ""
    import io

    src = io.BytesIO(ruta_o_bytes) if isinstance(ruta_o_bytes, bytes) else ruta_o_bytes
    return "\n".join((p.extract_text() or "") for p in PdfReader(src).pages)


class CarpetaLocal:
    """Vigila una carpeta (puede ser una carpeta sincronizada de Drive/OneDrive/Dropbox)."""

    def __init__(self, ruta: str, nombre: str = "carpeta_local") -> None:
        self.ruta = ruta
        self.nombre = nombre
        self._vistos: Set[str] = set()

    def nuevos_documentos(self) -> List[Documento]:
        docs: List[Documento] = []
        if not os.path.isdir(self.ruta):
            return docs
        for raiz, _, ficheros in os.walk(self.ruta):
            for nombre in sorted(ficheros):
                ruta = os.path.join(raiz, nombre)
                ext = os.path.splitext(nombre)[1].lower()
                if ruta in self._vistos or ext not in EXTENSIONES:
                    continue
                self._vistos.add(ruta)
                if ext == ".pdf":
                    texto = extraer_texto_pdf(ruta)
                else:
                    with open(ruta, encoding="utf-8", errors="replace") as fh:
                        texto = fh.read()
                docs.append(Documento(id=ruta, nombre=nombre, texto=texto, origen=self.nombre))
        return docs


class GoogleDrive:
    """Lee facturas de una carpeta de Google Drive.

    Requiere ``pip install agentes-contabilidad[google]`` y una cuenta de
    servicio con acceso a la carpeta (variable GOOGLE_APPLICATION_CREDENTIALS).
    """

    nombre = "google_drive"

    def __init__(self, carpeta_id: str, credenciales: Optional[str] = None) -> None:
        self.carpeta_id = carpeta_id
        self.credenciales = credenciales or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self._vistos: Set[str] = set()
        self._svc = None

    def _servicio(self):
        if self._svc is None:
            from google.oauth2 import service_account  # type: ignore
            from googleapiclient.discovery import build  # type: ignore

            creds = service_account.Credentials.from_service_account_file(
                self.credenciales, scopes=["https://www.googleapis.com/auth/drive.readonly"]
            )
            self._svc = build("drive", "v3", credentials=creds)
        return self._svc

    def nuevos_documentos(self) -> List[Documento]:
        svc = self._servicio()
        q = f"'{self.carpeta_id}' in parents and trashed = false"
        res = svc.files().list(q=q, fields="files(id,name,mimeType)").execute()
        docs = []
        for f in res.get("files", []):
            if f["id"] in self._vistos:
                continue
            self._vistos.add(f["id"])
            contenido = svc.files().get_media(fileId=f["id"]).execute()
            if f["name"].lower().endswith(".pdf"):
                texto = extraer_texto_pdf(contenido)
            else:
                texto = contenido.decode("utf-8", errors="replace")
            docs.append(Documento(id=f["id"], nombre=f["name"], texto=texto, origen=self.nombre))
        return docs


class BuzonIMAP:
    """Lee adjuntos de un buzón (p.ej. facturas@miempresa.es) vía IMAP."""

    nombre = "buzon_imap"

    def __init__(self, servidor: str, usuario: str, clave: str, carpeta: str = "INBOX") -> None:
        self.servidor, self.usuario, self.clave, self.carpeta = servidor, usuario, clave, carpeta

    def nuevos_documentos(self) -> List[Documento]:
        docs: List[Documento] = []
        with imaplib.IMAP4_SSL(self.servidor) as imap:
            imap.login(self.usuario, self.clave)
            imap.select(self.carpeta)
            _, ids = imap.search(None, "UNSEEN")
            for num in ids[0].split():
                _, data = imap.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])
                for parte in msg.walk():
                    nombre = parte.get_filename()
                    if not nombre:
                        continue
                    contenido = parte.get_payload(decode=True) or b""
                    texto = extraer_texto_pdf(contenido) if nombre.lower().endswith(".pdf") else contenido.decode("utf-8", "replace")
                    docs.append(Documento(
                        id=f"{num.decode()}:{nombre}", nombre=nombre, texto=texto, origen=self.nombre,
                        metadatos={"remitente": msg.get("From", ""), "asunto": msg.get("Subject", "")},
                    ))
        return docs
