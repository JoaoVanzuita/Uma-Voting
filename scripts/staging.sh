#!/usr/bin/env bash
#
# Sobe o ambiente de staging e expõe o site na internet via ngrok.
#
# - Usa o banco isolado config.settings.staging (padrão: uma_voting_staging).
# - Aplica migrations, garante cache e verifica a configuração.
# - Inicia o Django (runserver) e o worker de importação externa.
# - Abre o túnel ngrok e ajusta DJANGO_ALLOWED_HOSTS / CSRF para o domínio público.
# - Encerra todos os processos ao sair (Ctrl+C).
#
# Uso:
#   ./scripts/staging.sh
#   ./scripts/staging.sh --no-tunnel
#   ./scripts/staging.sh --port 8001 --domain staging.exemplo.com
#   ./scripts/staging.sh --fresh          # recria o banco de staging
#   ./scripts/staging.sh --reset-admin    # redefine a senha do admin
#
# Variáveis:
#   DEV_HOST                 host do runserver (padrão: 127.0.0.1)
#   DEV_PORT                 porta do runserver (padrão: 8000)
#   STAGING_POSTGRES_DB      nome do banco (padrão: uma_voting_staging)
#   STAGING_ADMIN_USERNAME   admin usado no --reset-admin (padrão: admin)
#   STAGING_ADMIN_PASSWORD   senha do --reset-admin (padrão: gerada e exibida)
#   NGROK_DOMAIN             domínio fixo do ngrok (opcional)
#   NGROK_AUTHTOKEN          token do ngrok; se ausente, usa a config local
#   EXTERNAL_IMPORT_ENABLED  kill switch (padrão: True neste ambiente)
#   POSTGRES_HOST/PORT       PostgreSQL (padrão: container db do Compose)
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DEV_HOST="${DEV_HOST:-127.0.0.1}"
DEV_PORT="${DEV_PORT:-8000}"
STAGING_POSTGRES_DB="${STAGING_POSTGRES_DB:-uma_voting_staging}"
USE_TUNNEL=1
FRESH=0
RESET_ADMIN=0
NGROK_DOMAIN="${NGROK_DOMAIN:-}"
EXPLICIT_POSTGRES_HOST="${POSTGRES_HOST:-}"

usage() {
  sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      DEV_HOST="${2:?Informe o host após --host}"
      shift 2
      ;;
    --port)
      DEV_PORT="${2:?Informe a porta após --port}"
      shift 2
      ;;
    --domain)
      NGROK_DOMAIN="${2:?Informe o domínio após --domain}"
      shift 2
      ;;
    --no-tunnel)
      USE_TUNNEL=0
      shift
      ;;
    --fresh)
      FRESH=1
      shift
      ;;
    --reset-admin)
      RESET_ADMIN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Opção desconhecida: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -f .env ]]; then
  echo "Arquivo .env não encontrado." >&2
  echo "Crie a partir do exemplo: cp .env.example .env" >&2
  exit 1
fi

# Carrega .env sem sobrescrever variáveis já definidas no ambiente.
set -a
# shellcheck disable=SC1091
. ./.env
set +a

if [[ -n "$EXPLICIT_POSTGRES_HOST" ]]; then
  POSTGRES_HOST="$EXPLICIT_POSTGRES_HOST"
fi

export DJANGO_SETTINGS_MODULE=config.settings.staging
export DJANGO_DEBUG=True
export PYTHONUNBUFFERED=1
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
export STAGING_POSTGRES_DB
export STAGING_DEBUG="${STAGING_DEBUG:-True}"
export EXTERNAL_IMPORT_ENABLED="${EXTERNAL_IMPORT_ENABLED:-True}"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON=("$ROOT/.venv/bin/python")
elif command -v uv >/dev/null 2>&1; then
  PYTHON=(uv run python)
else
  echo "Python do projeto não encontrado." >&2
  echo "Rode: uv sync" >&2
  exit 1
fi

port_open() {
  local host="$1"
  local port="$2"
  (exec 3<>"/dev/tcp/${host}/${port}") >/dev/null 2>&1
}

docker_available() {
  command -v docker >/dev/null 2>&1 &&
    docker compose version >/dev/null 2>&1 &&
    docker info >/dev/null 2>&1
}

db_container_id() {
  docker compose ps -q db 2>/dev/null || true
}

db_container_ip() {
  local container_id="$1"
  docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' "$container_id" 2>/dev/null || true
}

wait_for_db_container() {
  local container_id="$1"
  local status
  for _ in $(seq 1 30); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      return 0
    fi
    sleep 1
  done
  return 1
}

PIDS=()
cleanup() {
  local pid
  for pid in "${PIDS[@]:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# ---------------------------------------------------------------------------
# PostgreSQL
# ---------------------------------------------------------------------------
echo "==> Verificando PostgreSQL"

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "    usando DATABASE_URL do ambiente/.env"
elif [[ -n "${POSTGRES_HOST:-}" && "${POSTGRES_HOST}" != "db" ]] && port_open "${POSTGRES_HOST}" "${POSTGRES_PORT}"; then
  echo "    usando PostgreSQL em ${POSTGRES_HOST}:${POSTGRES_PORT}"
elif docker_available; then
  CONTAINER_ID="$(db_container_id)"
  if [[ -z "$CONTAINER_ID" ]]; then
    echo "    serviço db não está em execução; iniciando apenas o PostgreSQL..."
    docker compose up -d db
    CONTAINER_ID="$(db_container_id)"
  fi
  if [[ -z "$CONTAINER_ID" ]]; then
    echo "Não foi possível iniciar o serviço db do Compose." >&2
    exit 1
  fi
  if ! wait_for_db_container "$CONTAINER_ID"; then
    echo "O PostgreSQL não ficou pronto a tempo." >&2
    docker compose logs --tail 40 db >&2 || true
    exit 1
  fi
  POSTGRES_HOST="$(db_container_ip "$CONTAINER_ID")"
  if [[ -z "$POSTGRES_HOST" ]]; then
    echo "Não foi possível obter o IP do container PostgreSQL." >&2
    exit 1
  fi
  export POSTGRES_HOST
  echo "    usando PostgreSQL do Compose em ${POSTGRES_HOST}:${POSTGRES_PORT}"
elif port_open 127.0.0.1 "${POSTGRES_PORT}"; then
  POSTGRES_HOST=127.0.0.1
  export POSTGRES_HOST
  echo "    usando PostgreSQL local em 127.0.0.1:${POSTGRES_PORT}"
else
  echo "PostgreSQL não encontrado." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Banco de staging
# ---------------------------------------------------------------------------
if [[ "$FRESH" == "1" ]]; then
  echo "==> Recriando o banco ${STAGING_POSTGRES_DB}"
  "${PYTHON[@]}" - <<'PY'
import os

import psycopg

db = os.environ["STAGING_POSTGRES_DB"]
admin = psycopg.connect(
    host=os.environ["POSTGRES_HOST"],
    port=os.environ["POSTGRES_PORT"],
    dbname="postgres",
    user=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    autocommit=True,
)
with admin.cursor() as cursor:
    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", [db])
    if cursor.fetchone():
        cursor.execute(f'DROP DATABASE "{db}" WITH (FORCE)')
    cursor.execute(f'CREATE DATABASE "{db}"')
admin.close()
print(f"banco {db} recriado")
PY
fi

echo "==> Aplicando migrations em ${STAGING_POSTGRES_DB}"
"${PYTHON[@]}" manage.py migrate --noinput

echo "==> Garantindo tabela de cache"
"${PYTHON[@]}" manage.py createcachetable

# ---------------------------------------------------------------------------
# Administrador
# ---------------------------------------------------------------------------
if [[ "$RESET_ADMIN" == "1" ]]; then
  STAGING_ADMIN_USERNAME="${STAGING_ADMIN_USERNAME:-admin}"
  if [[ -z "${STAGING_ADMIN_PASSWORD:-}" ]]; then
    STAGING_ADMIN_PASSWORD="$("${PYTHON[@]}" -c 'import secrets; print(secrets.token_urlsafe(12))')"
  fi
  export STAGING_ADMIN_USERNAME STAGING_ADMIN_PASSWORD
  echo "==> Redefinindo o administrador ${STAGING_ADMIN_USERNAME}"
  "${PYTHON[@]}" manage.py shell -c '
import os
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ["STAGING_ADMIN_USERNAME"]
user, created = User.objects.get_or_create(
    username=username,
    defaults={"is_admin": True, "is_active": True},
)
user.is_admin = True
user.is_active = True
user.set_password(os.environ["STAGING_ADMIN_PASSWORD"])
user.save()
print(f"{username} {'criado' if created else 'atualizado'}")
'
  echo
  echo "    admin: ${STAGING_ADMIN_USERNAME}"
  echo "    senha: ${STAGING_ADMIN_PASSWORD}"
  echo
fi

# ---------------------------------------------------------------------------
# Túnel ngrok
# ---------------------------------------------------------------------------
PUBLIC_URL=""
if [[ "$USE_TUNNEL" == "1" ]]; then
  if ! command -v ngrok >/dev/null 2>&1; then
    echo "ngrok não encontrado; use --no-tunnel ou instale o ngrok." >&2
    exit 1
  fi

  echo "==> Abrindo túnel ngrok para http://127.0.0.1:${DEV_PORT}"
  NGROK_ARGS=(http "${DEV_PORT}" --log=stdout --log-format=json)
  if [[ -n "$NGROK_DOMAIN" ]]; then
    NGROK_ARGS+=(--domain "$NGROK_DOMAIN")
  fi
  if [[ -n "${NGROK_AUTHTOKEN:-}" ]]; then
    export NGROK_AUTHTOKEN
  fi

  LOG_FILE="$(mktemp -t uma-staging-ngrok.XXXXXX.log)"
  ngrok "${NGROK_ARGS[@]}" >"$LOG_FILE" 2>&1 &
  NGROK_PID=$!
  PIDS+=("$NGROK_PID")

  for _ in $(seq 1 40); do
    PUBLIC_URL="$("${PYTHON[@]}" - "$LOG_FILE" <<'PY'
import json
import sys

url = ""
with open(sys.argv[1], encoding="utf-8", errors="replace") as handle:
    for line in handle:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("url", "").startswith("https://"):
            url = event["url"]
print(url)
PY
)"
    if [[ -n "$PUBLIC_URL" ]]; then
      break
    fi
    if ! kill -0 "$NGROK_PID" 2>/dev/null; then
      break
    fi
    sleep 0.5
  done

  if [[ -z "$PUBLIC_URL" ]]; then
    echo "Não foi possível obter a URL pública do ngrok." >&2
    tail -20 "$LOG_FILE" >&2 || true
    exit 1
  fi
  echo "    URL pública: ${PUBLIC_URL}"
fi

# ---------------------------------------------------------------------------
# Hosts e CSRF
# ---------------------------------------------------------------------------
PUBLIC_HOST="${PUBLIC_URL#https://}"
export DJANGO_ALLOWED_HOSTS="localhost,127.0.0.1,${DEV_HOST}"
if [[ -n "$PUBLIC_HOST" ]]; then
  export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS},${PUBLIC_HOST}"
fi
export DJANGO_CSRF_TRUSTED_ORIGINS="http://localhost:${DEV_PORT},http://127.0.0.1:${DEV_PORT}"
if [[ -n "$PUBLIC_URL" ]]; then
  export DJANGO_CSRF_TRUSTED_ORIGINS="${DJANGO_CSRF_TRUSTED_ORIGINS},${PUBLIC_URL}"
fi
export SECURE_PROXY_SSL_HEADER="HTTP_X_FORWARDED_PROTO,https"

echo "==> Verificando configuração"
"${PYTHON[@]}" manage.py check

# ---------------------------------------------------------------------------
# Worker de importação
# ---------------------------------------------------------------------------
echo "==> Iniciando worker de importação externa"
"${PYTHON[@]}" manage.py run_import_worker --interval 5 --quiet &
PIDS+=("$!")

# ---------------------------------------------------------------------------
# Django
# ---------------------------------------------------------------------------
echo
echo "==> Staging em execução"
echo "    local:  http://localhost:${DEV_PORT}/"
if [[ -n "$PUBLIC_URL" ]]; then
  echo "    público: ${PUBLIC_URL}/"
  echo "    admin:   ${PUBLIC_URL}/admin/entrar/"
fi
echo "    banco:   ${STAGING_POSTGRES_DB}"
echo "    worker:  importação externa ativa (kill switch: EXTERNAL_IMPORT_ENABLED=${EXTERNAL_IMPORT_ENABLED})"
echo
echo "    Ctrl+C encerra o Django, o worker e o túnel."
echo

exec "${PYTHON[@]}" manage.py runserver "${DEV_HOST}:${DEV_PORT}"
