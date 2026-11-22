"""Headers de segurança replicados do Caddy para ambientes sem proxy próprio.

No Docker Compose o Caddy aplica CSP, HSTS e headers de isolamento. No Railway
não há Caddy: este middleware reproduz a mesma política quando
``SECURITY_HEADERS_MODE=django``.
"""

from __future__ import annotations

from django.conf import settings


def content_security_policy() -> str:
    """Monta a CSP com o host exato do bucket em ``img-src``."""
    img_sources = ["'self'", "data:"]
    bucket_source = getattr(settings, "MEDIA_CSP_SOURCE", "")
    if bucket_source:
        img_sources.append(bucket_source)
    return (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        f"img-src {' '.join(img_sources)}; "
        "font-src 'self'; "
        "connect-src 'self'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )


# Cabeçalhos aplicados pelo bloco ``header`` do Caddyfile. Os que o Django já
# emite (HSTS, X-Content-Type-Options) usam ``setdefault`` para não duplicar.
STATIC_HEADERS = {
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Content-Security-Policy": None,  # preenchido em runtime
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "X-Content-Type-Options": "nosniff",
}


class SecurityHeadersMiddleware:
    """Adiciona os headers do Caddy quando não há proxy no ambiente."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        for header, value in STATIC_HEADERS.items():
            if value is None:
                value = content_security_policy()
            response.setdefault(header, value)
        return response


# O healthcheck da plataforma (Railway) chega por HTTP interno, sem
# ``X-Forwarded-Proto``. Sem marcar a requisição como segura, o redirect de SSL
# de ``SecurityMiddleware`` responde 301 e o healthcheck nunca retorna 2xx.
PLATFORM_HEALTHCHECK_HOST = "healthcheck.railway.app"


class PlatformHealthcheckMiddleware:
    """Considera segura apenas a requisição de healthcheck da plataforma."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        is_https = request.META.get("HTTP_X_FORWARDED_PROTO") == "https"
        if (
            request.path == "/health/"
            and not is_https
            and request.get_host() == PLATFORM_HEALTHCHECK_HOST
        ):
            request.META["HTTP_X_FORWARDED_PROTO"] = "https"
        return self.get_response(request)
