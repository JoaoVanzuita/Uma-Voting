"""Testes do cliente HTTP allowlisted dos conectores externos."""

from __future__ import annotations

import json
import socket
import urllib.error

import pytest

from apps.catalog.services.sources.base import SourceDataError, SourceHTTPError
from apps.catalog.services.sources.http import HttpClient

PUBLIC_IP = "93.184.216.34"


class FakeResponse:
    def __init__(self, body: bytes = b"", status: int = 200, headers: dict | None = None):
        self._body = body
        self._position = 0
        self.status = status
        self.headers = headers or {}

    def read(self, amount: int = -1) -> bytes:
        if amount is None or amount < 0:
            amount = len(self._body) - self._position
        chunk = self._body[self._position : self._position + amount]
        self._position += len(chunk)
        return chunk

    def getcode(self) -> int:
        return self.status

    def close(self) -> None:
        pass


def public_dns(host, port, *args, **kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC_IP, port))]


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", public_dns)
    http = HttpClient(
        allowed_hosts=("example.com",),
        timeout=1,
        max_bytes=32,
        user_agent="test-agent",
        retries=3,
    )
    monkeypatch.setattr(http, "_sleep", lambda seconds: None)
    return http


def test_rejeita_http_sem_tls(client):
    with pytest.raises(SourceHTTPError, match="HTTPS"):
        client.get_bytes("http://example.com/data.json")


def test_rejeita_host_fora_da_allowlist(client):
    with pytest.raises(SourceHTTPError, match="não autorizado"):
        client.get_bytes("https://outro.example/data.json")


def test_rejeita_resolucao_para_ip_privado(client, monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.0.10", 443))
        ],
    )
    with pytest.raises(SourceHTTPError, match="não permitido"):
        client.get_bytes("https://example.com/data.json")


def test_segue_redirect_revalidando_destino(client, monkeypatch):
    responses = [
        FakeResponse(b"", status=302, headers={"Location": "https://outro.example/x"}),
    ]
    monkeypatch.setattr(client, "_open", lambda request: responses.pop(0))
    with pytest.raises(SourceHTTPError, match="não autorizado"):
        client.get_bytes("https://example.com/start")


def test_aplica_limite_de_bytes(client, monkeypatch):
    monkeypatch.setattr(client, "_open", lambda request: FakeResponse(b"x" * 64))
    with pytest.raises(SourceHTTPError, match="limite"):
        client.get_bytes("https://example.com/big.json")


def test_repete_em_503_e_depois_sucede(client, monkeypatch):
    responses = [FakeResponse(b"", status=503), FakeResponse(b"ok")]
    monkeypatch.setattr(client, "_open", lambda request: responses.pop(0))
    assert client.get_bytes("https://example.com/retry") == b"ok"


def test_esgota_tentativas_em_erro_persistente(client, monkeypatch):
    monkeypatch.setattr(client, "_open", lambda request: FakeResponse(b"", status=503))
    with pytest.raises(SourceHTTPError, match="503"):
        client.get_bytes("https://example.com/fail")


def test_erro_de_rede_e_convertido_em_source_http_error(client, monkeypatch):
    def raise_url_error(request):
        raise urllib.error.URLError("sem rota")

    monkeypatch.setattr(client, "_open", raise_url_error)
    with pytest.raises(SourceHTTPError, match="Falha de rede"):
        client.get_bytes("https://example.com/net")


def test_get_json_valida_conteudo(client, monkeypatch):
    payload = json.dumps({"ok": True}).encode()
    monkeypatch.setattr(client, "_open", lambda request: FakeResponse(payload))
    assert client.get_json("https://example.com/data.json") == {"ok": True}

    monkeypatch.setattr(client, "_open", lambda request: FakeResponse(b"<html>"))
    with pytest.raises(SourceDataError):
        client.get_json("https://example.com/invalid.json")


def test_cache_evita_segunda_requisicao(client, monkeypatch):
    calls = {"count": 0}

    def open_once(request):
        calls["count"] += 1
        return FakeResponse(b"ok")

    monkeypatch.setattr(client, "_open", open_once)
    client.get_bytes("https://example.com/cache")
    client.get_bytes("https://example.com/cache")
    assert calls["count"] == 1


def test_redirect_levantado_como_httperror_e_seguido(client, monkeypatch):
    redirect = urllib.error.HTTPError(
        "https://example.com/start",
        302,
        "Found",
        {"Location": "https://example.com/next"},
        None,
    )
    responses = [redirect, FakeResponse(b"ok")]
    monkeypatch.setattr(client, "_open", lambda request: responses.pop(0))

    assert client.get_bytes("https://example.com/start") == b"ok"


def test_limite_de_redirecionamentos(client, monkeypatch):
    def always_redirect(request):
        return FakeResponse(
            b"",
            status=302,
            headers={"Location": "https://example.com/loop"},
        )

    monkeypatch.setattr(client, "_open", always_redirect)

    with pytest.raises(SourceHTTPError, match="redirecionamentos"):
        client.get_bytes("https://example.com/start")
