"""Configurações usadas pela suíte de testes (PostgreSQL real)."""

from .base import *  # noqa: F403

DEBUG = False
ALLOWED_HOSTS = ["*"]
SECRET_KEY = "test-secret-key-nao-usar-em-producao"

# Hash rápido: os testes não avaliam a força do hash, apenas o fluxo.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# Testes nunca devem exigir TLS nem cookies seguros.
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
