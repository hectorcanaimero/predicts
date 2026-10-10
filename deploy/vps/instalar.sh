#!/usr/bin/env bash
# Prepara un VPS Ubuntu limpio para correr predicts: Docker Engine, firewall (solo 22/80/443
# abiertos) y un usuario sin privilegios de root para operar el stack. Idempotente: correrlo
# de nuevo no rompe nada ni duplica pasos ya hechos. Ver docs/notas/despliegue.md para el resto
# del despliegue (clonar el repo, completar deploy/.env, levantar el compose).
#
# Uso: sudo ./instalar.sh
set -euo pipefail

USUARIO_APP="${USUARIO_APP:-predicts}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Este script necesita privilegios de root: sudo ./instalar.sh" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive

echo "==> Actualizando paquetes del sistema"
apt-get update -y
apt-get upgrade -y

echo "==> Instalando dependencias base (curl, ufw)"
apt-get install -y ca-certificates curl gnupg ufw

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Instalando Docker Engine"
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc

  arquitectura="$(dpkg --print-architecture)"
  # shellcheck disable=SC1091  # /etc/os-release es del sistema, no del repo
  codename="$(. /etc/os-release && echo "$VERSION_CODENAME")"
  echo "deb [arch=${arquitectura} signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${codename} stable" \
    > /etc/apt/sources.list.d/docker.list

  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
  echo "==> Docker ya está instalado, se omite"
fi

echo "==> Configurando el firewall (ufw): solo 22/80/443"
ufw --force default deny incoming
ufw --force default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

if ! id "$USUARIO_APP" >/dev/null 2>&1; then
  echo "==> Creando el usuario sin privilegios '${USUARIO_APP}'"
  adduser --disabled-password --gecos "" "$USUARIO_APP"
else
  echo "==> El usuario '${USUARIO_APP}' ya existe, se omite la creación"
fi
usermod -aG docker "$USUARIO_APP"

cat <<MSG

==> Listo. Para desplegar predicts:

    su - ${USUARIO_APP}
    git clone https://github.com/hectorcanaimero/predicts.git
    cd predicts/deploy
    cp .env.example .env
    cat vps/.env.example >> .env   # completar SECRET_KEY/DOMINIO/SMTP_* antes de levantar
    docker compose -f docker-compose.yml -f vps/docker-compose.prod.yml up -d

Ver docs/notas/despliegue.md para el resto (actualización, restauración de backup, /salud).
MSG
