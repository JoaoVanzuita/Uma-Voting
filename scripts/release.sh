#!/bin/sh
# Etapa de release: roda uma vez antes de web/scheduler.
set -eu

python manage.py migrate --noinput
python manage.py createcachetable
python manage.py collectstatic --noinput

echo "Release concluído."
