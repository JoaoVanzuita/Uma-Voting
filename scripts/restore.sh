#!/bin/sh
# Restauração do banco e da mídia a partir de um backup.
#
# Uso:
#   RESTORE_CONFIRM=sim ./scripts/restore.sh /backups/db-AAAAMMDDTHHMMSSZ.dump \
#       /backups/media-AAAAMMDDTHHMMSSZ.tar.gz
#
# ATENÇÃO: sobrescreve o banco e os arquivos de mídia atuais.
set -eu

if [ "${RESTORE_CONFIRM:-nao}" != "sim" ]; then
  echo "Restauração cancelada. Defina RESTORE_CONFIRM=sim para confirmar." >&2
  exit 1
fi

if [ "$#" -ne 2 ]; then
  echo "Uso: $0 <arquivo.dump> <arquivo-media.tar.gz>" >&2
  exit 1
fi

DB_DUMP="$1"
MEDIA_ARCHIVE="$2"

POSTGRES_HOST="${POSTGRES_HOST:-db}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_DB="${POSTGRES_DB:-uma_voting}"
POSTGRES_USER="${POSTGRES_USER:-uma_voting}"
MEDIA_ROOT="${MEDIA_ROOT:-/app/media}"

echo "Restaurando banco ${POSTGRES_DB} a partir de ${DB_DUMP}"
pg_restore \
  --clean \
  --if-exists \
  --no-owner \
  --host="$POSTGRES_HOST" \
  --port="$POSTGRES_PORT" \
  --username="$POSTGRES_USER" \
  --dbname="$POSTGRES_DB" \
  "$DB_DUMP"

echo "Restaurando mídia em ${MEDIA_ROOT}"
mkdir -p "$MEDIA_ROOT"
tar -C "$(dirname "$MEDIA_ROOT")" -xzf "$MEDIA_ARCHIVE"

echo "Restauração concluída. Execute 'python manage.py migrate' e valide o healthcheck."
