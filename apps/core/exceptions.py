"""Exceções de domínio compartilhadas."""

from __future__ import annotations


class DomainError(Exception):
    """Erro de regra de negócio com mensagem segura para o usuário."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class PreconditionError(DomainError):
    """Pré-condição de operação não atendida."""


class NotFoundError(DomainError):
    """Recurso de domínio não encontrado."""
