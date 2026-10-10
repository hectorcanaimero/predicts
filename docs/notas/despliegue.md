# Despliegue en un VPS

Despliegue en un solo VPS Ubuntu con Docker Compose: el mismo stack de `docs/notas/desarrollo.md`
(`postgres`, `migrar`, `api`, `worker`, `web`) más **Caddy** como proxy con TLS automático delante
de `web` y un backup diario de Postgres (`deploy/vps/`). Ensayado de punta a punta con
`DOMINIO=localhost` (ver abajo) y validado con `docker compose config`.

## Requisitos mínimos del VPS

Límites de memoria por contenedor, iguales en homelab y VPS (`deploy/docker-compose.yml`,
medidos en `docs/notas/rendimiento.md` con 1 M y 5 M de filas):

| Servicio | `mem_limit` |
|---|---|
| `postgres` | 1 GB |
| `api` | 1 GB |
| `worker` | 5 GB |
| `web` | 256 MB |
| `caddy` | 256 MB |
| `backup` | 256 MB |

Suma de los límites: **≈ 7,75 GB**. `docs/notas/rendimiento.md` midió que el pico real en uso
(no el límite) queda muy por debajo de eso incluso con 5 M de filas (`worker` llegó a ≈ 1,94 GiB
de 5 GiB). Recomendado:

- **Mínimo:** 8 GB de RAM, 2 vCPU, 40 GB de disco (SSD) — para probar o para datasets de hasta
  ~1 M de filas con uso ocasional.
- **Cómodo:** 16 GB de RAM, 4 vCPU, 80 GB de disco — con margen para varios análisis a la vez y
  para que el sistema operativo y Docker no compitan por memoria con los límites de arriba.

Ubuntu 22.04 LTS o más nuevo, acceso root por SSH para correr `instalar.sh` una vez, y un dominio
propio apuntando al VPS (registro A/AAAA) si se quiere TLS real; `localhost` sirve para el ensayo
con el certificado interno de Caddy (ver "Ensayo local" abajo).

## Pasos

1. **Preparar el VPS** (una sola vez, como root): instala Docker Engine, abre el firewall solo
   para 22/80/443 y crea un usuario sin privilegios (`predicts` por defecto) para operar el stack.

   ```bash
   scp deploy/vps/instalar.sh root@TU_VPS:
   ssh root@TU_VPS './instalar.sh'
   ```

2. **Clonar el repo y completar las variables**, ya como el usuario sin privilegios:

   ```bash
   ssh predicts@TU_VPS
   git clone https://github.com/hectorcanaimero/predicts.git
   cd predicts/deploy
   cp .env.example .env
   cat vps/.env.example >> .env
   ```

   Editar `.env` y completar, como mínimo:
   - `SECRET_KEY` (generarla con `openssl rand -hex 32`, nunca reusar la de desarrollo).
   - `DOMINIO`: el dominio público que apunta a este VPS (Caddy pide el certificado real para
     ese nombre).
   - `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD`/`SMTP_FROM`: obligatorias en producción
     (sin ellas, los emails de recuperación de contraseña no salen — el override de producción
     falla al validar el compose si falta alguna, ver abajo).
   - `ROUTER_*`/`TYPESAFE_*` si se quiere IA real (mapeo, mensajes, agente analista); sin ellas
     el sistema sigue funcionando pero esas decisiones caen a su comportamiento sin servicio
     externo (ver `CONTEXTO.md`).

   > `docker compose` lee un solo `.env`, el que está junto al primer archivo pasado con `-f`
   > (`deploy/.env`). Por eso `vps/.env.example` se pega al final de `deploy/.env` en vez de
   > vivir en un `.env` separado dentro de `deploy/vps/`.

3. **Validar y levantar:**

   ```bash
   docker compose -f docker-compose.yml -f vps/docker-compose.prod.yml config   # valida sin tocar nada
   docker compose -f docker-compose.yml -f vps/docker-compose.prod.yml up -d --build
   ```

   Caddy pide el certificado TLS (Let's Encrypt) para `DOMINIO` la primera vez que arranca;
   mirar `docker compose -f docker-compose.yml -f vps/docker-compose.prod.yml logs -f caddy` si
   tarda. El resto de los servicios funciona igual que en `docs/notas/desarrollo.md`.

## Ensayo local (sin VPS real)

Con `DOMINIO=localhost` en `deploy/.env`, Caddy detecta que no es un dominio público y usa su
propia autoridad certificadora interna en vez de pedirle un certificado a Let's Encrypt — no
hace falta ningún dominio de prueba ni DNS. Igual que en el paso 3, pero en la máquina local:

```bash
cd deploy
cp .env.example .env && cat vps/.env.example >> .env
# completar SECRET_KEY y SMTP_* con cualquier valor (no salen emails reales sin un SMTP real)
docker compose -f docker-compose.yml -f vps/docker-compose.prod.yml up -d --build
curl -k https://localhost/api/salud   # certificado "Caddy Local Authority", no de confianza del navegador: -k para ignorarlo
```

Si el puerto 443 del host ya está en uso por otro proceso (por ejemplo una VPN que lo reserva),
Caddy no puede levantar — es un conflicto de puertos del host de prueba, no del compose; en un
VPS limpio (el caso real que cubre `instalar.sh`) 443 está libre.

## Actualización

```bash
cd predicts
git pull
docker compose -f deploy/docker-compose.yml -f deploy/vps/docker-compose.prod.yml up -d --build
```

`migrar` corre `alembic upgrade head` antes de que `api`/`worker` arranquen (ver
`deploy/docker-compose.yml`); no hace falta ningún paso manual de migración.

## Restauración de un backup

El servicio `backup` (`deploy/vps/backup.sh`) guarda un dump comprimido por día en el volumen
`postgres_backups`, con `RETENCION_BACKUPS_DIAS` (7 por defecto) días de retención.

```bash
# Ver los backups disponibles
docker compose -f deploy/docker-compose.yml -f deploy/vps/docker-compose.prod.yml exec backup \
  ls -la /backups

# Restaurar uno (bajar api/worker primero para que no escriban durante la restauración)
docker compose -f deploy/docker-compose.yml -f deploy/vps/docker-compose.prod.yml stop api worker
docker compose -f deploy/docker-compose.yml -f deploy/vps/docker-compose.prod.yml exec backup \
  sh -c 'gunzip -c /backups/predicts_YYYYMMDD_HHMMSS.sql.gz | psql -h postgres -U "$PGUSER" -d "$PGDATABASE"'
docker compose -f deploy/docker-compose.yml -f deploy/vps/docker-compose.prod.yml start api worker
```

## Monitoreo básico

`GET /salud` (`api/src/predicts/api/salud.py`) devuelve `200` con `{"ok": true, "postgres": true,
"data_dir": true}` cuando Postgres responde y `DATA_DIR` existe, o `503` con el campo que falló
en `false` si no. A través del proxy:

```bash
curl -s https://TU_DOMINIO/api/salud
```

Para un chequeo periódico sin herramientas nuevas, un cron del propio VPS alcanza:

```cron
*/5 * * * * curl -fs https://TU_DOMINIO/api/salud > /dev/null || echo "predicts caído" | mail -s "predicts" tu@email
```

`docker stats --no-stream` (mismo comando que en `docs/notas/desarrollo.md`) para ver memoria y
CPU de cada contenedor contra su `mem_limit`.
