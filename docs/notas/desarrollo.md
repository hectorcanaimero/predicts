# Desarrollo: levantar todo, tests contra Postgres, logs

## Levantar la app completa (docker compose)

```bash
cd deploy
cp .env.example .env   # completar ROUTER_*/TYPESAFE_* si se necesita IA real; el resto anda con defaults
docker compose config  # valida el archivo sin tocar nada
docker compose build
docker compose up -d postgres migrar api web
```

- `postgres`: `pgvector/pgvector:pg17`, puerto publicado `${POSTGRES_PORT:-54320}` → 5432.
- `migrar`: corre `alembic upgrade head` una vez y sale (`service_completed_successfully`); `api`
  y `worker` esperan a que termine antes de arrancar.
- `api`: FastAPI con uvicorn, puerto publicado `${API_PORT:-8000}`.
- `web`: build de Vite + nginx, puerto publicado `${WEB_PORT:-8080}`; nginx proxea `/api/` a `api`
  (sin buffering en `/api/trabajos/` para SSE, ver `deploy/nginx.conf`).
- `worker`: definido con `command: ["predicts", "worker"]` y el límite de memoria de la
  arquitectura (5 GB), pero ese comando todavía no existe en el CLI — lo agrega una fase
  posterior. No lo incluyas en el `up` hasta entonces.

Verificar que responde a través de nginx:

```bash
curl -s http://localhost:${WEB_PORT:-8080}/api/salud
```

Memoria de cada contenedor en reposo (anotar en el PR cuando se valida esta tarea):

```bash
docker stats --no-stream
```

Bajar todo al terminar:

```bash
docker compose down
```

## Correr tests contra `predicts-pg-dev`

El homelab ya tiene un Postgres de desarrollo corriendo fuera de este compose: contenedor
`predicts-pg-dev` (`pgvector/pgvector:pg17`) en `127.0.0.1:54329`, usuario y contraseña
`predicts`. Los tests marcados `db` (ver `api/tests/conftest_db.py`) crean su propia base
temporal (`predicts_test_<uuid>`) a partir de `TEST_DATABASE_URL` y la borran al terminar, así
que varios worktrees pueden correr tests en paralelo sin pisarse.

```bash
cd api
export TEST_DATABASE_URL="postgresql+psycopg://predicts:predicts@127.0.0.1:54329/postgres"
uv run pytest -q
```

Los worktrees de orch no tienen `.env`: si algún comando necesita `Settings` completo (no solo
los tests con `db`), apuntar `PREDICTS_ENV_FILE=/mnt/storage/project/predicts/.env` (tiene las
claves reales de 9router/Jev). Nunca copiar ni imprimir esos valores.

## Dónde mirar los logs

- **Stack de `deploy/docker-compose.yml`:**
  ```bash
  docker compose -f deploy/docker-compose.yml logs -f api      # o worker, web, postgres, migrar
  ```
- **`predicts-pg-dev` (Postgres del homelab, fuera de este compose):**
  ```bash
  docker logs -f predicts-pg-dev
  ```
- **Eventos de un trabajo** (cuando exista la cola, fase F3+): tabla `eventos_trabajo` en
  Postgres, y vía SSE en `GET /trabajos/{id}/eventos` (proxeado como `/api/trabajos/{id}/eventos`
  por nginx).
