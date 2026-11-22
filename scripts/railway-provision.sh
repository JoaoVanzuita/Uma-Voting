#!/usr/bin/env bash
#
# Fase 2 — provisionamento e deploy inicial no Railway.
#
# O provisionamento de recursos (Postgres, Bucket, serviço web, variáveis,
# pre-deploy, healthcheck) é descrito por Infrastructure as Code em
# `.railway/railway.ts`. Este script só orquestra a CLI e a validação.
#
# Pré-requisitos (uma vez, manual):
#   - Railway CLI: npm install --global @railway/cli@5.75.0
#   - `railway login`
#   - Projeto + ambiente `production` criados/linkados (`railway link`).
#
# Nenhum segredo é gravado em arquivo: este script envia os segredos direto
# para o Railway. Evite rodar com `bash -x`.
#
# Uso:
#   ./scripts/railway-provision.sh plan            # revisa o plano (não altera)
#   ./scripts/railway-provision.sh apply           # aplica o IaC (confirma)
#   ./scripts/railway-provision.sh secrets         # grava segredos/hosts do web
#   ./scripts/railway-provision.sh deploy          # deploy manual inicial
#   ./scripts/railway-provision.sh health          # healthchecks público/interno
#   ./scripts/railway-provision.sh migrate-media   # media/ -> bucket
#   ./scripts/railway-provision.sh status          # resumo dos recursos
#   ./scripts/railway-provision.sh all             # plan + secrets + deploy
#
# Variáveis:
#   RAILWAY_ENVIRONMENT  ambiente (padrão: production)
#   RAILWAY_SERVICE      serviço web (padrão: web)
#   RAILWAY_BUCKET       bucket de mídia (padrão: uma-voting-media)
#   APP_HOST             domínio público gerado (obrigatório para secrets/health)
#   ALLOWED_HOSTS        hosts extras, separados por vírgula (opcional)
#   SECRET_KEY           segredo do Django (padrão: gerado com openssl)
#   APPLY_MEDIA=1        permite o envio efetivo da mídia no passo migrate-media
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

ENVIRONMENT="${RAILWAY_ENVIRONMENT:-production}"
SERVICE="${RAILWAY_SERVICE:-web}"
BUCKET="${RAILWAY_BUCKET:-uma-voting-media}"
STEP="${1:-all}"

log() { printf '==> %s\n' "$*"; }
die() { printf 'erro: %s\n' "$*" >&2; exit 1; }

require_railway() {
  command -v railway >/dev/null 2>&1 || die "Railway CLI ausente: npm install --global @railway/cli@5.75.0"
  railway whoami >/dev/null 2>&1 || die "Sem login. Rode: railway login"
  [ -f .railway/railway.ts ] || die ".railway/railway.ts ausente."
}

variable() {
  railway variable list --environment "$ENVIRONMENT" --service "$SERVICE" --json \
    | python3 -c "import json,sys; print(json.load(sys.stdin).get('$1',''))"
}

gravar_segredos() {
  require_railway
  [ -n "${APP_HOST:-}" ] || die "Defina APP_HOST com o domínio gerado (railway domain)."

  local secret_key="${SECRET_KEY:-$(openssl rand -base64 48 | tr -d '\n')}"
  local hosts="$APP_HOST,healthcheck.railway.app${ALLOWED_HOSTS:+,$ALLOWED_HOSTS}"
  local service_arg=(--service "$SERVICE")

  log "Gravando segredos e hosts no serviço $SERVICE"
  railway variable set "DJANGO_SECRET_KEY=$secret_key" "${service_arg[@]}" --skip-deploys
  railway variable set "DJANGO_ALLOWED_HOSTS=$hosts" "${service_arg[@]}" --skip-deploys
  railway variable set "DJANGO_CSRF_TRUSTED_ORIGINS=https://$APP_HOST" "${service_arg[@]}" --skip-deploys

  local endpoint bucket_name
  endpoint="$(variable AWS_S3_ENDPOINT_URL)"
  bucket_name="$(variable AWS_STORAGE_BUCKET_NAME)"
  [ -n "$endpoint" ] && [ -n "$bucket_name" ] || die "Bucket ainda não referenciado no serviço; aplique o IaC."
  log "Liberando o host do bucket no CSP"
  railway variable set "MEDIA_CSP_SOURCE=https://${bucket_name}.${endpoint#https://}" \
    "${service_arg[@]}" --skip-deploys
}

deploy_inicial() {
  require_railway
  log "Deploy manual inicial (build + pre-deploy + healthcheck)"
  railway up --environment "$ENVIRONMENT" --service "$SERVICE"
}

validar_health() {
  require_railway
  [ -n "${APP_HOST:-}" ] || die "Defina APP_HOST."
  log "Healthcheck público"
  curl --fail --silent --show-error --retry 6 --retry-delay 10 --retry-all-errors \
    "https://$APP_HOST/health/"
  echo
  log "Healthcheck interno com o host da plataforma (healthcheck.railway.app)"
  # Simula o healthcheck interno: HTTP local com o Host da plataforma.
  railway ssh --environment "$ENVIRONMENT" --service "$SERVICE" -- \
    sh -c 'python -c "import os, urllib.request as u; r = u.Request(\"http://127.0.0.1:%s/health/\" % os.environ.get(\"PORT\", \"8000\"), headers={\"Host\": \"healthcheck.railway.app\"}); print(u.urlopen(r, timeout=10).read().decode())"' || \
    log "Healthcheck interno falhou; confira os logs do serviço (a versão anterior segue ativa)."
}

migrar_media() {
  require_railway
  log "Lendo credenciais do bucket (exportadas apenas no shell atual)"
  eval "$(railway bucket credentials --environment "$ENVIRONMENT" --bucket "$BUCKET")"
  export MEDIA_STORAGE_BACKEND=s3
  export AWS_STORAGE_BUCKET_NAME="${AWS_S3_BUCKET_NAME:-}"
  export AWS_S3_REGION_NAME="${AWS_DEFAULT_REGION:-auto}"
  # O credentials da CLI usa "virtual-host"; o django-storages espera "virtual".
  local style="${AWS_S3_URL_STYLE:-virtual}"
  export AWS_S3_ADDRESSING_STYLE="${style/virtual-host/virtual}"
  export AWS_S3_ENDPOINT_URL="${AWS_ENDPOINT_URL:-}"

  # O banco não é necessário: o manifesto lista os arquivos locais.
  local manifest
  manifest="$(mktemp -t uma-media.XXXXXX.csv)"
  python3 - "$manifest" <<'PY'
import pathlib, sys
root = pathlib.Path("media")
rows = ["character_stable_id,file"]
for path in sorted(root.joinpath("characters").rglob("*.webp")):
    relative = path.relative_to(root).as_posix()
    rows.append(f"{relative.split('/')[1]},{relative}")
pathlib.Path(sys.argv[1]).write_text("\n".join(rows) + "\n", encoding="utf-8")
print(f"{len(rows) - 1} imagens no manifesto")
PY

  log "dry-run"
  uv run python manage.py migrate_media_to_storage --dry-run \
    --source-root ./media --manifest "$manifest"
  if [ "${APPLY_MEDIA:-0}" != "1" ]; then
    log "Nada enviado. Use APPLY_MEDIA=1 para aplicar."
    return
  fi
  log "apply"
  uv run python manage.py migrate_media_to_storage --apply \
    --source-root ./media --manifest "$manifest"
}

status() {
  require_railway
  railway status --environment "$ENVIRONMENT"
  railway bucket list --environment "$ENVIRONMENT"
  railway bucket info --environment "$ENVIRONMENT" --bucket "$BUCKET" --json
}

case "$STEP" in
  plan)
    require_railway
    railway config plan --environment "$ENVIRONMENT" --show-values
    ;;
  apply)
    require_railway
    log "Revisando o plano antes de aplicar"
    railway config plan --environment "$ENVIRONMENT" --show-values
    log "Aplicando Infrastructure as Code"
    railway config apply --environment "$ENVIRONMENT" --yes
    ;;
  secrets) gravar_segredos ;;
  deploy) deploy_inicial ;;
  health) validar_health ;;
  migrate-media) migrar_media ;;
  status) status ;;
  all)
    require_railway
    railway config plan --environment "$ENVIRONMENT" --show-values
    railway config apply --environment "$ENVIRONMENT" --yes
    gravar_segredos
    deploy_inicial
    ;;
  *) die "Passo desconhecido: $STEP (all|plan|apply|secrets|deploy|health|migrate-media|status)" ;;
esac
