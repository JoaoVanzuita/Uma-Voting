"""Throttle de login com DatabaseCache (compartilhado entre workers)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from django.core.cache import cache

WINDOW_SECONDS = 5 * 60

ADMIN_USER_LIMIT = 5
ADMIN_IP_LIMIT = 20
PARTICIPANT_IP_LIMIT = 20

_CACHE_PREFIX = "login-throttle"


@dataclass(frozen=True)
class ThrottleResult:
    allowed: bool
    retry_after: int = 0


def _validate_scope(scope: str) -> None:
    if scope not in {"admin", "participant"}:
        raise ValueError(f"Escopo de throttle desconhecido: {scope}")


def _username_key(scope: str, ip: str, username: str) -> str:
    digest = hashlib.sha256(f"{ip[:64]}|{username.strip().casefold()}".encode()).hexdigest()[:16]
    return f"{_CACHE_PREFIX}:{scope}:user:{digest}"


def _ip_key(scope: str, ip: str) -> str:
    return f"{_CACHE_PREFIX}:{scope}:ip:{ip[:64]}"


def _counter(key: str) -> int:
    return int(cache.get(key, 0) or 0)


def _increment(key: str) -> None:
    if cache.add(key, 1, WINDOW_SECONDS):
        return
    try:
        cache.incr(key)
    except ValueError:
        # A chave expirou entre o add e o incr; reinicia a janela.
        cache.set(key, 1, WINDOW_SECONDS)


def check_login_allowed(scope: str, ip: str, username: str | None = None) -> ThrottleResult:
    """Verifica os limites sem incrementar contadores."""
    _validate_scope(scope)

    limits = [(_ip_key(scope, ip), ADMIN_IP_LIMIT if scope == "admin" else PARTICIPANT_IP_LIMIT)]
    if scope == "admin" and username:
        limits.append((_username_key(scope, ip, username), ADMIN_USER_LIMIT))

    blocked = any(_counter(key) >= limit for key, limit in limits)
    return ThrottleResult(allowed=not blocked, retry_after=WINDOW_SECONDS if blocked else 0)


def register_attempt(scope: str, ip: str, username: str | None = None) -> None:
    """Registra uma tentativa/falha dentro da janela de 5 minutos."""
    _validate_scope(scope)

    _increment(_ip_key(scope, ip))
    if scope == "admin" and username:
        _increment(_username_key(scope, ip, username))


def clear_attempts(scope: str, ip: str, username: str | None = None) -> None:
    """Limpa os contadores relevantes após um login bem-sucedido."""
    _validate_scope(scope)

    if scope == "admin":
        if username:
            cache.delete(_username_key(scope, ip, username))
        return

    cache.delete(_ip_key(scope, ip))


def get_client_ip(request) -> str:
    """IP do cliente atrás do Caddy; o proxy sobrescreve X-Forwarded-For."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return (request.META.get("REMOTE_ADDR") or "0.0.0.0")[:64]
