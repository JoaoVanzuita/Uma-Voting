"""Configuração compartilhada da suíte de testes (PostgreSQL real)."""

import http.client
import urllib.request
from urllib.parse import urlsplit

import pytest

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testserver"}


def _is_loopback(host: str | None) -> bool:
    """Considera loopback apenas endereços locais usados pela própria suíte."""
    normalized = str(host or "").strip("[]").lower()
    if normalized in _LOOPBACK_HOSTS:
        return True
    return normalized.startswith("127.")


@pytest.fixture(autouse=True)
def block_external_network(monkeypatch):
    """Impede chamadas de rede reais durante os testes.

    A importação externa deve ser exercitada com o cliente HTTP mockado. Testes
    que precisem de servidor local continuam funcionando via loopback.
    """
    original_connect = http.client.HTTPConnection.connect
    original_urlopen = urllib.request.urlopen

    def guarded_connect(connection):
        if not _is_loopback(connection.host):
            raise RuntimeError(
                "Chamada de rede externa bloqueada nos testes: "
                f"{connection.host}. Use um cliente HTTP mockado."
            )
        return original_connect(connection)

    def guarded_urlopen(url, *args, **kwargs):
        target = url.full_url if isinstance(url, urllib.request.Request) else str(url)
        host = urlsplit(target).hostname
        if not _is_loopback(host):
            raise RuntimeError(
                f"Chamada de rede externa bloqueada nos testes: {host}. "
                "Use um cliente HTTP mockado."
            )
        return original_urlopen(url, *args, **kwargs)

    monkeypatch.setattr(http.client.HTTPConnection, "connect", guarded_connect)
    monkeypatch.setattr(urllib.request, "urlopen", guarded_urlopen)
    yield


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
