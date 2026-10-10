"""Comando `predicts worker`: procesa la cola de trabajos (ver `predicts.trabajos.worker`)."""

from __future__ import annotations

import logging

from predicts.comandos import comando
from predicts.config import settings
from predicts.trabajos import registro
from predicts.trabajos.worker import correr


@comando
def worker() -> None:
    """Toma trabajos de la cola y ejecuta cada uno en un subproceso con tope de memoria."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    registro.descubrir()
    s = settings()
    correr(s.DATABASE_URL, s.MAX_MEMORIA_TRABAJO_MB, s.TIMEOUT_TRABAJO_S)
