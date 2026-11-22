"""Configurações de produção (atrás de proxy HTTPS: Caddy ou plataforma).

Em ambos os casos a aplicação exige TLS, cookies seguros e HSTS. A diferença é
o healthcheck interno: plataformas como o Railway consultam ``/health/`` por
HTTP, sem ``X-Forwarded-Proto``; com ``DJANGO_SECURE_REDIRECT_EXEMPT_HEALTH`` a
própria aplicação aceita só essa rota por HTTP.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import SECRET_KEY, env

DEBUG = False

if SECRET_KEY == "insecure-dev-key-change-me" or len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("Defina DJANGO_SECRET_KEY com pelo menos 50 caracteres em produção.")

ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=None)
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("Defina DJANGO_ALLOWED_HOSTS em produção.")

CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = 31_536_000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # o HTMX lê o token do cookie

# ---------------------------------------------------------------------------
# Deploy sem proxy próprio (ex.: Railway): estáticos pelo WhiteNoise, headers
# de segurança do Caddy em Django e scheduler acionado por requisição.
# ---------------------------------------------------------------------------
if MEDIA_STORAGE_BACKEND == "s3":  # noqa: F405
    _missing_s3 = [
        name
        for name, value in {
            "AWS_S3_ENDPOINT_URL": env("AWS_S3_ENDPOINT_URL"),
            "AWS_ACCESS_KEY_ID": env("AWS_ACCESS_KEY_ID"),
            "AWS_SECRET_ACCESS_KEY": env("AWS_SECRET_ACCESS_KEY"),
            "AWS_STORAGE_BUCKET_NAME": env("AWS_STORAGE_BUCKET_NAME"),
        }.items()
        if not value
    ]
    if _missing_s3:
        raise ImproperlyConfigured(
            "MEDIA_STORAGE_BACKEND=s3 exige: " + ", ".join(_missing_s3) + "."
        )

if env.bool("DJANGO_SECURE_REDIRECT_EXEMPT_HEALTH", default=False):
    MIDDLEWARE = [  # noqa: F405
        "apps.core.security_headers.PlatformHealthcheckMiddleware"
        if item == "django.middleware.security.SecurityMiddleware"
        else item
        for item in MIDDLEWARE  # noqa: F405
    ]
