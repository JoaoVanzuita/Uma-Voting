"""Serviços de autenticação de administradores e participantes."""

from __future__ import annotations

import logging
import math

from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError

from apps.accounts.models import User
from apps.accounts.services.throttle import (
    check_login_allowed,
    clear_attempts,
    get_client_ip,
    register_attempt,
)
from apps.core.middleware import ADMIN_MODE_SESSION_KEY

logger = logging.getLogger("apps.accounts.auth")

MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"

ADMIN_ERROR = "Username ou senha inválidos."
PARTICIPANT_ERROR = "Não foi possível entrar com esse username."


class AuthError(Exception):
    """Erro de autenticação com mensagem segura para exibição."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class InvalidCredentialsError(AuthError):
    pass


class ThrottleError(AuthError):
    def __init__(self, retry_after: int) -> None:
        self.retry_after = max(1, int(retry_after))
        minutes = max(1, math.ceil(self.retry_after / 60))
        super().__init__(f"Muitas tentativas de acesso. Tente novamente em {minutes} minuto(s).")


def create_admin(username: str, password: str) -> User:
    """Cria um administrador com senha utilizável e username único."""
    username = (username or "").strip()
    if not username:
        raise ValueError("O username é obrigatório.")
    if len(username) > 150:
        raise ValueError("O username deve ter no máximo 150 caracteres.")
    if not password:
        raise ValueError("A senha é obrigatória.")
    if User.objects.filter(username__iexact=username).exists():
        raise ValueError("Já existe um usuário com esse username.")

    try:
        user = User.objects.create_superuser(username=username, password=password)
    except IntegrityError as exc:
        raise ValueError("Já existe um usuário com esse username.") from exc

    logger.info("Administrador criado user_id=%s", user.pk)
    return user


def login_admin(request, username: str, password: str) -> User:
    """Autentica administrador com senha, throttle e sessão rotacionada."""
    ip = get_client_ip(request)
    result = check_login_allowed("admin", ip, username)
    if not result.allowed:
        logger.warning("Login administrativo bloqueado por throttle ip=%s", ip)
        raise ThrottleError(result.retry_after)

    user = authenticate(request, username=username, password=password)
    if user is None or not user.is_active or not getattr(user, "is_admin", False):
        register_attempt("admin", ip, username)
        logger.warning("Falha de login administrativo ip=%s", ip)
        raise InvalidCredentialsError(ADMIN_ERROR)

    clear_attempts("admin", ip, username)
    login(request, user, backend=MODEL_BACKEND)
    request.session[ADMIN_MODE_SESSION_KEY] = False
    logger.info("Login administrativo concluído user_id=%s", user.pk)
    return user


def login_participant(request, username: str) -> User:
    """Login de participante por username, com throttle por IP.

    Username inexistente, usuário inativo e username administrativo recebem a
    mesma mensagem genérica. O acesso não comprova identidade.
    """
    username = (username or "").strip()
    ip = get_client_ip(request)
    result = check_login_allowed("participant", ip)
    if not result.allowed:
        logger.warning("Login de participante bloqueado por throttle ip=%s", ip)
        raise ThrottleError(result.retry_after)

    register_attempt("participant", ip)

    user = User.objects.filter(username__iexact=username).first() if username else None
    if user is None or not user.is_active or user.is_admin:
        logger.warning("Falha de login de participante ip=%s", ip)
        raise InvalidCredentialsError(PARTICIPANT_ERROR)

    login(request, user, backend=MODEL_BACKEND)
    request.session.pop(ADMIN_MODE_SESSION_KEY, None)
    logger.info("Login de participante concluído user_id=%s", user.pk)
    return user


def logout_user(request) -> None:
    user = getattr(request, "user", None)
    user_id = user.pk if user is not None and user.is_authenticated else None
    logout(request)
    logger.info("Logout concluído user_id=%s", user_id)
