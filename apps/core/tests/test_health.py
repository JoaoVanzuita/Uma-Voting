"""Smoke tests de infraestrutura: healthcheck, request ID e página 404."""

import pytest


@pytest.mark.django_db
def test_health_responde_com_banco_ok(client):
    response = client.get("/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "db": "ok"}
    assert response["Cache-Control"] == "no-store"


@pytest.mark.django_db
def test_health_retorna_503_quando_banco_falha(client, monkeypatch):
    class BrokenConnection:
        def cursor(self):
            raise RuntimeError("banco indisponível")

    monkeypatch.setattr("apps.core.views.connection", BrokenConnection())

    response = client.get("/health/")

    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "db": "error"}


def test_request_id_informado_e_devolvido(client):
    response = client.get("/nao-existe/", headers={"X-Request-ID": "abc-123_DEF"})

    assert response["X-Request-ID"] == "abc-123_DEF"


def test_request_id_invalido_e_substituido(client):
    response = client.get("/nao-existe/", headers={"X-Request-ID": "<script>"})

    request_id = response["X-Request-ID"]
    assert request_id != "<script>"
    assert len(request_id) == 32


def test_pagina_404_usa_template_pt_br(client):
    response = client.get("/nao-existe/")

    assert response.status_code == 404
    assert "Página não encontrada" in response.content.decode()
