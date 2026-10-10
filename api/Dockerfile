# syntax=docker/dockerfile:1

# Imagen de build: `uv` + Python 3.13 para resolver e instalar dependencias desde `uv.lock`.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Capa de dependencias por separado del código: cambia menos seguido, cachea mejor.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY README.md ./
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Imagen final: solo el venv ya resuelto, sin `uv` ni toolchain de build. Sirve tanto a
# `api` (`predicts api`) como a `worker` (`predicts worker`), con el `command` en compose.
FROM python:3.13-slim AS runtime

RUN groupadd --system predicts \
    && useradd --system --gid predicts --home-dir /app --shell /usr/sbin/nologin predicts \
    && mkdir -p /data \
    && chown predicts:predicts /data

WORKDIR /app
COPY --from=builder --chown=predicts:predicts /app /app

ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

USER predicts
EXPOSE 8000

CMD ["predicts", "api", "--host", "0.0.0.0", "--port", "8000"]
