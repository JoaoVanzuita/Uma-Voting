"""Serviços de gestão de participantes."""

from __future__ import annotations

from django.db import IntegrityError

from apps.accounts.models import User
from apps.core.exceptions import DomainError


class ParticipantError(DomainError):
    pass


def _normalize_username(username: str) -> str:
    value = (username or "").strip()
    if not value:
        raise ParticipantError("O username é obrigatório.")
    if len(value) > 150:
        raise ParticipantError("O username deve ter no máximo 150 caracteres.")
    return value


def _username_exists(username: str, *, exclude_id: int | None = None) -> bool:
    queryset = User.objects.filter(username__iexact=username)
    if exclude_id is not None:
        queryset = queryset.exclude(pk=exclude_id)
    return queryset.exists()


def create_participant(username: str) -> User:
    """Cria participante ativo, não administrativo e sem senha utilizável."""
    username = _normalize_username(username)
    if _username_exists(username):
        raise ParticipantError("Já existe um usuário com esse username.")

    try:
        return User.objects.create_user(username=username)
    except IntegrityError as exc:
        raise ParticipantError("Já existe um usuário com esse username.") from exc


def update_participant(user: User, username: str) -> User:
    """Atualiza o username de um participante, nunca de um administrador."""
    if user.is_admin:
        raise ParticipantError(
            "Contas administrativas são somente leitura na área de participantes."
        )

    username = _normalize_username(username)
    if _username_exists(username, exclude_id=user.pk):
        raise ParticipantError("Já existe um usuário com esse username.")

    user.username = username
    try:
        user.save(update_fields=["username"])
    except IntegrityError as exc:
        raise ParticipantError("Já existe um usuário com esse username.") from exc
    return user


def deactivate_participant(user: User) -> User:
    """Desativa um participante sem alterar elegibilidades já existentes."""
    if user.is_admin:
        raise ParticipantError(
            "Contas administrativas são somente leitura na área de participantes."
        )

    if user.is_active:
        user.is_active = False
        user.save(update_fields=["is_active"])
    return user
