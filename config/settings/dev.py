"""Configurações de desenvolvimento local."""

from .base import *  # noqa: F403
from .base import _with_conditionals

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Em desenvolvimento o Django serve estáticos e mídia; em produção o Caddy assume.
INTERNAL_IPS = ["127.0.0.1", "localhost"]

# Cookies sem Secure para permitir HTTP local.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# runserver serve os estáticos com auto-reload; WhiteNoise (manifest) só existe
# na imagem de deploy do Railway.
_BASE_MIDDLEWARE = MIDDLEWARE  # noqa: F405 - herdado de base
MIDDLEWARE = [
    item for item in _with_conditionals(_BASE_MIDDLEWARE) if not item.startswith("whitenoise.")
]
