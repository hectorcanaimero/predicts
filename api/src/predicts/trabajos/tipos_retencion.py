"""Tipo de trabajo `retencion` (ver specs/f8-3d-demo-despliegue.md#F8.3.T2): aplica
`predicts.retencion.limpiar` a los datasets de una empresa.

`encolar_si_corresponde` es lo que reemplaza al cron externo: el worker la llama en cada vuelta
de su loop (`trabajos.worker.correr`), y si ya pasó `INTERVALO_ENCOLADO` desde el último
`retencion` encolado (de cualquier empresa), encola uno por empresa.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from predicts.config import settings
from predicts.db.modelos import Empresa, Trabajo
from predicts.retencion import limpiar
from predicts.trabajos import cola, eventos
from predicts.trabajos.registro import TrabajoEnCurso, tipo_trabajo

INTERVALO_ENCOLADO = timedelta(hours=1)


@tipo_trabajo("retencion")
def retencion(trabajo: TrabajoEnCurso) -> None:
    """Archiva los datasets vencidos de la empresa del trabajo y limpia `DATA_DIR/tmp`."""
    engine = eventos._engine()
    with Session(engine) as db:
        resultado = limpiar(db, settings(), empresa_id=trabajo.empresa_id)
    eventos.emitir(
        trabajo.id,
        "retencion",
        {
            "datasets_archivados": len(resultado.datasets_archivados),
            "tmp_borrados": len(resultado.tmp_borrados),
        },
    )


def encolar_si_corresponde(db: Session, *, ahora: datetime | None = None) -> int:
    """Encola un trabajo `retencion` por empresa si ya pasó `INTERVALO_ENCOLADO` desde el
    último. Devuelve cuántos encoló (0 si todavía no toca)."""
    ahora = ahora or datetime.now(UTC)
    ultimo = db.scalar(
        select(Trabajo.creado_en)
        .where(Trabajo.tipo == "retencion")
        .order_by(Trabajo.creado_en.desc())
        .limit(1)
    )
    if ultimo is not None and ahora - ultimo < INTERVALO_ENCOLADO:
        return 0
    empresas = db.scalars(select(Empresa.id)).all()
    for empresa_id in empresas:
        cola.encolar(db, empresa_id, "retencion", {})
    return len(empresas)
