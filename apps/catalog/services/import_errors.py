"""Exceções de negócio da importação externa.

Mantidas em módulo próprio para que registry e serviços possam importá-las sem
dependência circular.
"""

from __future__ import annotations


class ImportJobError(Exception):
    """Erro de negócio da importação externa."""


class ImportJobStateError(ImportJobError):
    """Ação inválida para o estado atual da execução (HTTP 409)."""


class ImportSourceError(ImportJobError):
    """Fonte inválida, desabilitada ou sem conector registrado."""


class ImportDisabledError(ImportJobError):
    """Importação externa desligada pelo kill switch."""
