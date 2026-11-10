"""Envío de correo: simulado (bandeja de salida en disco) o SMTP real."""
from __future__ import annotations

import os
import smtplib
from datetime import datetime
from email.message import EmailMessage
from typing import List, Optional

from ..models import EmailSaliente


class CorreoSimulado:
    """No envía nada: guarda los correos en memoria y, opcionalmente, como .eml."""

    def __init__(self, carpeta_salida: Optional[str] = None) -> None:
        self.enviados: List[EmailSaliente] = []
        self.carpeta = carpeta_salida
        if self.carpeta:
            os.makedirs(self.carpeta, exist_ok=True)

    def enviar(self, email: EmailSaliente) -> None:
        email.enviado_en = datetime.now()
        self.enviados.append(email)
        if self.carpeta:
            with open(os.path.join(self.carpeta, f"{email.id}.eml"), "w", encoding="utf-8") as fh:
                fh.write(f"To: {email.para}\nSubject: {email.asunto}\n\n{email.cuerpo}\n")


class CorreoSMTP:
    def __init__(self, servidor: str, puerto: int, usuario: str, clave: str, remitente: str) -> None:
        self.servidor, self.puerto = servidor, puerto
        self.usuario, self.clave, self.remitente = usuario, clave, remitente

    def enviar(self, email: EmailSaliente) -> None:
        msg = EmailMessage()
        msg["From"] = self.remitente
        msg["To"] = email.para
        msg["Subject"] = email.asunto
        msg.set_content(email.cuerpo)
        for ruta in email.adjuntos:
            with open(ruta, "rb") as fh:
                msg.add_attachment(fh.read(), maintype="application", subtype="octet-stream",
                                   filename=os.path.basename(ruta))
        with smtplib.SMTP(self.servidor, self.puerto) as s:
            s.starttls()
            s.login(self.usuario, self.clave)
            s.send_message(msg)
        email.enviado_en = datetime.now()
