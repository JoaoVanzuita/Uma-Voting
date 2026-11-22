#!/bin/sh
# Pre-Deploy Command do Railway (configurado no Dashboard, não em railway.json).
#
# Executa em um container separado: o filesystem não é persistido e não há
# volume montado. Por isso apenas migrações e a tabela de cache; o
# collectstatic acontece no build da imagem (Dockerfile).
set -eu

python manage.py migrate --noinput
python manage.py createcachetable --verbosity 0

echo "Pre-deploy Railway concluído."
