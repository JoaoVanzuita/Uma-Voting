#!/usr/bin/env bash
#
# Executa o Django fora do Docker.
#
# - Usa o PostgreSQL do Docker Compose quando necessário (sobe apenas o serviço db).
# - Também aceita PostgreSQL local ou DATABASE_URL.
# - Executa migrate/createcachetable/check antes de iniciar.
# - Inicia manage.py runserver com auto-reload em 0.0.0.0:8000.
#
# Uso:
#   ./scripts/dev.sh
#   DEV_PORT=8001 ./scripts/dev.sh
#   ./scripts/dev.sh --port 8001 --host 127.0.0.1
#   ./scripts/dev.sh --stop-web
#
# Variáveis:
#   DEV_HOST              host do runserver (padrão: 0.0.0.0)
#   DEV_PORT              porta do runserver (padrão: 8000)
#   POSTGRES_HOST         host explícito do PostgreSQL (sobrepõe o .env)
#   POSTGRES_PORT         porta do PostgreSQL (padrão: 5432)
#   DATABASE_URL          URL completa; tem precedência sobre POSTGRES_*
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

DEV_HOST="${DEV_HOST:-0.0.0.0}"
DEV_PORT="${DEV_PORT:-8000}"
STOP_WEB=0
RUN_MIGRATIONS=1
EXPLICIT_POSTGRES_HOST="${POSTGRES_HOST:-}"

usage() {
  sed -n '2,22p' "$0" | sed 's/^# \{0,1\}//'
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
    --stop-web)
      STOP_WEB=1
      shift
      ;;
    --no-migrate)
      RUN_MIGRATIONS=0
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

# Permite que POSTGRES_HOST definido antes da leitura do .env prevaleça.
if [[ -n "$EXPLICIT_POSTGRES_HOST" ]]; then
  POSTGRES_HOST="$EXPLICIT_POSTGRES_HOST"
fi

export DJANGO_SETTINGS_MODULE=config.settings.dev
export DJANGO_DEBUG=True
export PYTHONUNBUFFERED=1
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
export POSTGRES_HOST
EXTRA_ORIGINS="http://localhost:${DEV_PORT},http://127.0.0.1:${DEV_PORT}"
if [[ -n "${DJANGO_CSRF_TRUSTED_ORIGINS:-}" ]]; then
  export DJANGO_CSRF_TRUSTED_ORIGINS="${DJANGO_CSRF_TRUSTED_ORIGINS},${EXTRA_ORIGINS}"
else
  export DJANGO_CSRF_TRUSTED_ORIGINS="${EXTRA_ORIGINS}"
fi

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

echo "==> Verificando PostgreSQL"

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "    usando DATABASE_URL do ambiente/.env"
elif [[ -n "${POSTGRES_HOST:-}" && "${POSTGRES_HOST}" != "db" ]] && port_open "${POSTGRES_HOST}" "${POSTGRES_PORT:-5432}"; then
  echo "    usando PostgreSQL em ${POSTGRES_HOST}:${POSTGRES_PORT:-5432}"
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
  if ! port_open "$POSTGRES_HOST" "$POSTGRES_PORT"; then
    echo "O container PostgreSQL não está aceitando conexões em ${POSTGRES_HOST}:${POSTGRES_PORT}." >&2
    exit 1
  fi
  echo "    usando PostgreSQL do Compose em ${POSTGRES_HOST}:${POSTGRES_PORT}"
elif port_open 127.0.0.1 "${POSTGRES_PORT:-5432}"; then
  POSTGRES_HOST=127.0.0.1
  export POSTGRES_HOST
  echo "    usando PostgreSQL local em 127.0.0.1:${POSTGRES_PORT:-5432}"
else
  echo "PostgreSQL não encontrado." >&2
  echo "Opções:" >&2
  echo "  - inicie o Docker Compose: docker compose up -d db" >&2
  echo "  - ou defina POSTGRES_HOST/POSTGRES_PORT para um PostgreSQL local" >&2
  exit 1
fi

if [[ "$STOP_WEB" == "1" ]]; then
  echo "==> Parando web/scheduler do Compose para evitar conflito na porta ${DEV_PORT}"
  docker compose stop web scheduler >/dev/null 2>&1 || true
fi

if port_open 127.0.0.1 "$DEV_PORT"; then
  echo "A porta ${DEV_PORT} já está em uso." >&2
  echo "Se for o container web do Compose, execute:" >&2
  echo "  docker compose stop web scheduler" >&2
  echo "Ou use outra porta:" >&2
  echo "  DEV_PORT=8001 ./scripts/dev.sh" >&2
  echo "Ou peça ao script para parar web/scheduler:" >&2
  echo "  ./scripts/dev.sh --stop-web" >&2
  exit 1
fi

if [[ "$RUN_MIGRATIONS" == "1" ]]; then
  echo "==> Aplicando migrations"
  "${PYTHON[@]}" manage.py migrate --noinput
fi

echo "==> Garantindo tabela de cache"
"${PYTHON[@]}" manage.py createcachetable

echo "==> Verificando configuração"
"${PYTHON[@]}" manage.py check

echo
echo "==> Django fora do Docker em http://localhost:${DEV_PORT}/"
echo "    Auto-reload ativo. Para CSS/JS antigo no navegador, use Ctrl+Shift+R."
echo

exec "${PYTHON[@]}" manage.py runserver "${DEV_HOST}:${DEV_PORT}"
