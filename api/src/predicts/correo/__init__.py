"""Envío de correo: SMTP con `SMTP_*` si está configurada, si no escribe el email completo en
el log (modo dev, ver docs/arch/001-predicts.md#config). Plantillas de texto e HTML en
`correo/plantillas/<idioma>/<nombre>.{txt,html}`, elegidas por el idioma del usuario."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path

from predicts.config import settings

logger = logging.getLogger(__name__)

_DIR_PLANTILLAS = Path(__file__).parent / "plantillas"
IDIOMAS = ("pt-BR", "es", "en")


def _leer_plantilla(idioma: str, nombre: str, extension: str) -> str:
    return (_DIR_PLANTILLAS / idioma / f"{nombre}.{extension}").read_text(encoding="utf-8")


def renderizar(idioma: str, nombre: str, contexto: dict[str, str]) -> tuple[str, str, str]:
    """`(asunto, texto, html)` de la plantilla `nombre` en `idioma`. La primera línea del `.txt`
    es el asunto; el resto es el cuerpo. `contexto` se interpola con `str.format`."""
    asunto, cuerpo_texto = _leer_plantilla(idioma, nombre, "txt").split("\n", 1)
    html = _leer_plantilla(idioma, nombre, "html")
    return asunto.strip().format(**contexto), cuerpo_texto.strip().format(**contexto), html.format(
        **contexto
    )


def enviar(destinatario: str, idioma: str, nombre_plantilla: str, contexto: dict[str, str]) -> None:
    asunto, texto, html = renderizar(idioma, nombre_plantilla, contexto)

    cfg = settings()
    if not cfg.SMTP_HOST:
        logger.info("Email (modo dev) a %s\nAsunto: %s\n\n%s", destinatario, asunto, texto)
        return

    mensaje = EmailMessage()
    mensaje["Subject"] = asunto
    mensaje["From"] = cfg.SMTP_FROM or cfg.SMTP_USER or "no-reply@predicts"
    mensaje["To"] = destinatario
    mensaje.set_content(texto)
    mensaje.add_alternative(html, subtype="html")

    with smtplib.SMTP(cfg.SMTP_HOST, cfg.SMTP_PORT or 587) as smtp:
        if cfg.SMTP_USER:
            smtp.starttls()
            smtp.login(cfg.SMTP_USER, cfg.SMTP_PASSWORD or "")
        smtp.send_message(mensaje)
