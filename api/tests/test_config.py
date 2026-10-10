"""Tests de `predicts.config`: defaults, lectura de .env, overrides y validaciones."""

import pytest
from pydantic import ValidationError

from predicts.config import settings, settings_para_tests


@pytest.fixture(autouse=True)
def _limpiar_cache_y_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PREDICTS_ENV_FILE", raising=False)
    settings.cache_clear()
    yield
    settings.cache_clear()


def test_defaults() -> None:
    cfg = settings_para_tests()
    assert cfg.ENTORNO == "dev"
    assert cfg.SECRET_KEY is None
    assert cfg.ROUTER_EMBEDDINGS_MODEL == "openai/text-embedding-3-small"
    assert cfg.TYPESAFE_MODEL == "jev-latest"
    assert cfg.MAX_CSV_MB == 500
    assert cfg.MIN_COMPRAS == 3
    assert cfg.HORIZONTE_DIAS == 7
    assert cfg.VENTANA_VALIDACION_SEMANAS == 4
    assert cfg.CONFIANZA_MAPEO == 0.8
    assert cfg.CONFIANZA_JEV == 0.7
    assert cfg.RETENCION_DIAS == 7
    assert cfg.DUCKDB_MEMORY_LIMIT == "3GB"
    assert cfg.DUCKDB_THREADS == 4
    assert cfg.MAX_MEMORIA_TRABAJO_MB == 4096
    assert cfg.TIMEOUT_TRABAJO_S == 1800
    assert cfg.SMTP_HOST is None


def test_settings_cacheada_devuelve_la_misma_instancia(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql://u:p@localhost/db\n"
        "DATA_DIR=/tmp/data\n"
        "ROUTER_BASE_URL=https://router\n"
        "ROUTER_API_KEY=k\n"
        "ROUTER_MODEL=m\n"
        "TYPESAFE_API_KEY=k\n"
    )
    monkeypatch.setenv("PREDICTS_ENV_FILE", str(env))
    assert settings() is settings()


def test_lectura_desde_predicts_env_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / "custom.env"
    env.write_text(
        "DATABASE_URL=postgresql://u:p@localhost/db\n"
        "DATA_DIR=/tmp/data\n"
        "ROUTER_BASE_URL=https://router\n"
        "ROUTER_API_KEY=k\n"
        "ROUTER_MODEL=m\n"
        "TYPESAFE_API_KEY=k\n"
        "MIN_COMPRAS=9\n"
    )
    monkeypatch.setenv("PREDICTS_ENV_FILE", str(env))
    cfg = settings()
    assert cfg.DATABASE_URL == "postgresql://u:p@localhost/db"
    assert cfg.MIN_COMPRAS == 9


def test_lectura_desde_env_del_cwd(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "DATABASE_URL=postgresql://u:p@localhost/db\n"
        "DATA_DIR=/tmp/data\n"
        "ROUTER_BASE_URL=https://router\n"
        "ROUTER_API_KEY=k\n"
        "ROUTER_MODEL=m\n"
        "TYPESAFE_API_KEY=k\n"
    )
    monkeypatch.chdir(tmp_path)
    cfg = settings()
    assert cfg.DATABASE_URL == "postgresql://u:p@localhost/db"


def test_overrides_por_entorno() -> None:
    cfg = settings_para_tests(ENTORNO="prod", SECRET_KEY="s3cr3t", MIN_COMPRAS=5)
    assert cfg.ENTORNO == "prod"
    assert cfg.MIN_COMPRAS == 5


@pytest.mark.parametrize("valor", ["3", "3TB", "GB", "3 GB", ""])
def test_duckdb_memory_limit_formato_invalido(valor: str) -> None:
    with pytest.raises(ValidationError):
        settings_para_tests(DUCKDB_MEMORY_LIMIT=valor)


@pytest.mark.parametrize("valor", ["3GB", "512MB", "0GB"])
def test_duckdb_memory_limit_formato_valido(valor: str) -> None:
    cfg = settings_para_tests(DUCKDB_MEMORY_LIMIT=valor)
    assert cfg.DUCKDB_MEMORY_LIMIT == valor


def test_max_memoria_trabajo_mb_debe_ser_mayor_a_512() -> None:
    with pytest.raises(ValidationError):
        settings_para_tests(MAX_MEMORIA_TRABAJO_MB=512)
    assert settings_para_tests(MAX_MEMORIA_TRABAJO_MB=513).MAX_MEMORIA_TRABAJO_MB == 513


@pytest.mark.parametrize("campo", ["CONFIANZA_MAPEO", "CONFIANZA_JEV"])
@pytest.mark.parametrize("valor", [-0.01, 1.01])
def test_confianza_debe_estar_entre_0_y_1(campo: str, valor: float) -> None:
    with pytest.raises(ValidationError):
        settings_para_tests(**{campo: valor})


@pytest.mark.parametrize("campo", ["CONFIANZA_MAPEO", "CONFIANZA_JEV"])
def test_confianza_en_los_bordes_es_valida(campo: str) -> None:
    assert settings_para_tests(**{campo: 0.0})
    assert settings_para_tests(**{campo: 1.0})


def test_secret_key_obligatoria_fuera_de_dev() -> None:
    with pytest.raises(ValidationError):
        settings_para_tests(ENTORNO="prod")
    assert settings_para_tests(ENTORNO="prod", SECRET_KEY="s3cr3t")


def test_secret_key_no_es_obligatoria_en_dev() -> None:
    cfg = settings_para_tests(ENTORNO="dev")
    assert cfg.SECRET_KEY is None
