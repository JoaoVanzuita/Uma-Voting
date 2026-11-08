#!/bin/sh
# Sincronização periódica do catálogo a partir de um arquivo curado.
#
# Uso:
#   CATALOG_FILE=/app/var/catalog.csv ./scripts/sync_catalog.sh
#
# Variáveis:
#   CATALOG_FILE   (padrão /app/var/catalog.csv)
#   CATALOG_SOURCE (padrão curadoria-local)
set -eu

CATALOG_FILE="${CATALOG_FILE:-/app/var/catalog.csv}"
CATALOG_SOURCE="${CATALOG_SOURCE:-curadoria-local}"

if [ ! -f "$CATALOG_FILE" ]; then
  echo "Arquivo de catálogo não encontrado: $CATALOG_FILE" >&2
  exit 1
fi

echo "Sincronizando catálogo $CATALOG_FILE (fonte=$CATALOG_SOURCE)"
python manage.py sync_catalog --source "$CATALOG_SOURCE" --file "$CATALOG_FILE"
echo "Sincronização concluída."
