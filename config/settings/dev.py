"""Configurações de desenvolvimento local."""

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# Em desenvolvimento o Django serve estáticos e mídia; em produção o Caddy assume.
INTERNAL_IPS = ["127.0.0.1", "localhost"]

# Cookies sem Secure para permitir HTTP local.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
