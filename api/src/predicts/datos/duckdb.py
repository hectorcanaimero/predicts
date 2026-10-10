"""Conexión DuckDB con los límites de memoria, hilos y temporales de la configuración."""

from __future__ import annotations

from pathlib import Path

import duckdb

from predicts.config import Settings, settings


def conexion_duckdb(
    solo_lectura: bool = False, cfg: Settings | None = None
) -> duckdb.DuckDBPyConnection:
    """Conexión DuckDB en memoria con `memory_limit`, `threads` y `temp_directory`
    (`DATA_DIR/tmp`) tomados de `Settings`.

    `cfg` permite inyectar una `Settings` de test en vez de la global cacheada.
    `solo_lectura` queda reservado para cuando el agente (F7) abra un archivo
    DuckDB persistente en modo lectura: DuckDB no admite `read_only` sobre una
    base ``:memory:``, así que por ahora el parámetro no cambia nada.
    """
    cfg = cfg or settings()
    tmp_dir = Path(cfg.DATA_DIR) / "tmp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(":memory:")
    con.execute(f"SET memory_limit = '{cfg.DUCKDB_MEMORY_LIMIT}'")
    con.execute(f"SET threads = {cfg.DUCKDB_THREADS}")
    con.execute(f"SET temp_directory = '{tmp_dir}'")
    return con
