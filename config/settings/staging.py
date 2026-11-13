"""Configurações de staging: banco isolado para testes ponta a ponta.

Herda de ``dev`` para que o próprio Django sirva estáticos e mídia (não há
Caddy nesse perfil). O banco é separado do banco de desenvolvimento e pode ser
descartado ao final dos testes.

Uso:
    DJANGO_SETTINGS_MODULE=config.settings.staging ./scripts/dev.sh

Variáveis:
    STAGING_POSTGRES_DB   nome do banco (padrão: uma_voting_staging)
    STAGING_DEBUG         "True" para servir estáticos/mídia (padrão: True)
"""

from .base import env
from .dev import *  # noqa: F403
from .dev import DATABASES

STAGING_POSTGRES_DB = env("STAGING_POSTGRES_DB", default="uma_voting_staging")
DATABASES["default"]["NAME"] = STAGING_POSTGRES_DB

DEBUG = env.bool("STAGING_DEBUG", default=True)
