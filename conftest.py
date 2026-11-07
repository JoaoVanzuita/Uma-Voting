"""Configuração compartilhada da suíte de testes (PostgreSQL real)."""

import pytest


@pytest.fixture
def cache_table(db):
    """Garante a tabela do DatabaseCache no banco de teste."""
    from django.core.management import call_command

    call_command("createcachetable", verbosity=0)
    yield


def pytest_report_header(config):
    """Deixa explícito que os testes exigem PostgreSQL, nunca SQLite."""
    from django.conf import settings

    engine = settings.DATABASES["default"]["ENGINE"]
    return f"banco de teste: {engine}"
