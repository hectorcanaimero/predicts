#!/usr/bin/env bash
# Entrypoint del servicio `backup` de deploy/vps/docker-compose.prod.yml: un dump diario de
# Postgres (PGHOST/PGUSER/PGPASSWORD/PGDATABASE vienen de ese compose) a /backups, con
# retención de RETENCION_BACKUPS_DIAS días. Sin cron externo: el propio contenedor hace el
# primer dump al arrancar y después uno por día mientras viva (restart: unless-stopped lo
# vuelve a levantar si se cae).
set -euo pipefail

DESTINO="/backups"
RETENCION_DIAS="${RETENCION_BACKUPS_DIAS:-7}"

mkdir -p "$DESTINO"

while true; do
  archivo="${DESTINO}/predicts_$(date -u +%Y%m%d_%H%M%S).sql.gz"
  echo "[backup] $(date -u -Iseconds) volcando a ${archivo}"
  pg_dump --no-owner --no-privileges | gzip > "$archivo"
  find "$DESTINO" -name 'predicts_*.sql.gz' -mtime "+${RETENCION_DIAS}" -delete
  sleep 86400
done
