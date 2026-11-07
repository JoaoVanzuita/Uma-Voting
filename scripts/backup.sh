#!/bin/sh
# Backup do banco (pg_dump -Fc) e do acervo de mídia (tar).
#
# Uso:
#   docker compose exec -T db sh -c 'pg_dump ...'   (alternativa)
#   ./scripts/backup.sh
#
# Variáveis: POSTGRES_HOST, POSTGRES_PORT, POSTGRES_DB, POSTGRES_USER,
#            BACKUP_DIR (padrão /backups), MEDIA_ROOT (padrão /app/media)
set -eu

POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-uma_voting}"
POSTGRES_USER="${POSTGRES_USER:-uma_voting}"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
MEDIA_ROOT="${MEDIA_ROOT:-/app/media}"
TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_DIR"

echo "Gerando backup do banco em ${BACKUP_DIR}/db-${TIMESTAMP}.dump"
pg_dump \
  --format=custom \
  --host="$POSTGRES_HOST" \
  --port="$POSTGRES_PORT" \
  --username="$POSTGRES_USER" \
  --dbname="$POSTGRES_DB" \
  --file="${BACKUP_DIR}/db-${TIMESTAMP}.dump"

echo "Gerando backup da mídia em ${BACKUP_DIR}/media-${TIMESTAMP}.tar.gz"
tar -C "$(dirname "$MEDIA_ROOT")" -czf "${BACKUP_DIR}/media-${TIMESTAMP}.tar.gz" \
  "$(basename "$MEDIA_ROOT")"

echo "Backup concluído: ${TIMESTAMP}"
