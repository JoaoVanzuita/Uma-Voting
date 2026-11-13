#!/usr/bin/env bash
# Executa o inventário visual em uma instância isolada.
#
# - Clona o banco local para `uma_voting_screens` (o banco principal não é tocado).
# - Sobe um runserver descartável em http://127.0.0.1:8001.
# - Cria o cenário determinístico com seed.py.
# - Executa o Playwright e grava as imagens/manifesto em var/screenshots/.
#
# Variáveis opcionais:
#   SCREENSHOT_BASE_URL   (padrão: http://127.0.0.1:8001)
#   PLAYWRIGHT_CHROMIUM   caminho do executável do Chromium
#   KEEP_SCREENSHOT_CONTAINER=1  mantém o container no final para inspeção
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

SCREEN_DB="${SCREEN_DB:-uma_voting_screens}"
CONTAINER="${SCREEN_CONTAINER:-uma-voting-screens}"
PORT="${SCREEN_PORT:-8001}"
BASE_URL="${SCREENSHOT_BASE_URL:-http://127.0.0.1:${PORT}}"
OUTPUT="$ROOT/var/screenshots"
HARNESS="$ROOT/var/screenshot-harness"

cleanup() {
  if [[ "${KEEP_SCREENSHOT_CONTAINER:-0}" != "1" ]]; then
    docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

echo "==> Recriando banco isolado ${SCREEN_DB}"
docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
DB_CONTAINER="$(docker compose ps -q db)"
if [[ -z "$DB_CONTAINER" ]]; then
  echo "O serviço db não está em execução. Suba a stack local antes de continuar." >&2
  exit 1
fi
NETWORK="${SCREEN_NETWORK:-$(docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' "$DB_CONTAINER")}"
MEDIA_VOLUME="${SCREEN_MEDIA_VOLUME:-$(docker volume ls --format '{{.Name}}' | grep -E 'uma-voting_media_data$' | head -n1)}"
if [[ -z "$NETWORK" || -z "$MEDIA_VOLUME" ]]; then
  echo "Não foi possível detectar a rede ou o volume de mídia do Compose." >&2
  exit 1
fi

docker compose exec -T db psql -U "${POSTGRES_USER:-uma_voting}" -d postgres \
  -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${SCREEN_DB}' AND pid <> pg_backend_pid();" >/dev/null
docker compose exec -T db psql -U "${POSTGRES_USER:-uma_voting}" -d postgres \
  -c "DROP DATABASE IF EXISTS ${SCREEN_DB};"
docker compose exec -T db psql -U "${POSTGRES_USER:-uma_voting}" -d postgres \
  -c "CREATE DATABASE ${SCREEN_DB};"
docker compose exec -T db sh -c \
  "pg_dump -U ${POSTGRES_USER:-uma_voting} -d ${POSTGRES_DB:-uma_voting} --no-owner --no-privileges" \
  | docker compose exec -T db psql -U "${POSTGRES_USER:-uma_voting}" -d "${SCREEN_DB}" >/tmp/uma-voting-screens-clone.log

echo "==> Subindo instância isolada em ${BASE_URL}"
docker run -d --name "$CONTAINER" \
  --network "$NETWORK" \
  -p "${PORT}:8000" \
  -v "$ROOT":/app \
  -v "${MEDIA_VOLUME}":/app/media \
  --env-file .env \
  -e DJANGO_SETTINGS_MODULE=config.settings.dev \
  -e DJANGO_DEBUG=True \
  -e POSTGRES_HOST=db \
  -e POSTGRES_DB="$SCREEN_DB" \
  -e DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1 \
  -e DJANGO_CSRF_TRUSTED_ORIGINS="${BASE_URL},http://localhost:${PORT}" \
  uma-voting:latest python manage.py runserver 0.0.0.0:8000 --noreload >/dev/null

echo -n "==> Aguardando healthcheck"
for _ in $(seq 1 40); do
  if curl -fsS "${BASE_URL}/health/" >/dev/null 2>&1; then
    echo " ok"
    break
  fi
  echo -n "."
  sleep 1
done
curl -fsS "${BASE_URL}/health/" >/dev/null || {
  echo
  echo "A instância não respondeu em ${BASE_URL}." >&2
  docker logs --tail 80 "$CONTAINER" >&2 || true
  exit 1
}

mkdir -p "$OUTPUT/fixtures" "$OUTPUT/png"
chmod -R 777 "$OUTPUT" 2>/dev/null || true

echo "==> Criando cenário de screenshots"
docker exec -i "$CONTAINER" python manage.py shell < \
  "$ROOT/tests/e2e/screenshot_inventory/seed.py"

echo "==> Garantindo Playwright"
mkdir -p "$HARNESS"
if [[ ! -d "$HARNESS/node_modules/playwright" ]]; then
  (cd "$HARNESS" && npm init -y >/dev/null 2>&1 && npm install playwright@1.65.0 --no-audit --no-fund)
fi
if ! ls "$HOME"/.cache/ms-playwright/chromium-*/chrome-linux64/chrome >/dev/null 2>&1; then
  echo "==> Baixando Chromium do Playwright"
  (cd "$HARNESS" && ./node_modules/.bin/playwright install chromium)
fi

echo "==> Capturando telas"
(
  cd "$HARNESS"
  NODE_PATH="$HARNESS/node_modules" \
  SCREENSHOT_BASE_URL="$BASE_URL" \
  SCREENSHOT_OUTPUT="$OUTPUT" \
  node "$ROOT/tests/e2e/screenshot_inventory/capture.js"
)

if [[ "${SKIP_QA:-0}" != "1" ]]; then
  echo "==> Auditoria de acessibilidade e responsividade"
  (
    cd "$HARNESS"
    NODE_PATH="$HARNESS/node_modules" \
    SCREENSHOT_BASE_URL="$BASE_URL" \
    SCREENSHOT_OUTPUT="$OUTPUT" \
    node "$ROOT/tests/e2e/screenshot_inventory/qa.js"
  )
fi

echo
echo "Inventário disponível em:"
echo "  $OUTPUT/index.html"
echo "  $OUTPUT/manifest.json"
echo "  $OUTPUT/qa-report.json"
