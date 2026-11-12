"""Smoke tests das telas administrativas de importação externa."""

from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import ImportJob
from apps.catalog.services.importers import CatalogParseReport
from apps.catalog.services.sources.base import SourceCheckResult
from apps.catalog.services.sources.registry import ADAPTERS
from tests.factories import AdminUserFactory, CatalogSourceFactory, ImportJobFactory

pytestmark = pytest.mark.django_db


class FakeAdapter:
    key = "fake-source"
    display_name = "Fonte falsa"
    allowed_hosts = ()

    def __init__(self, source):
        self.source = source

    def fetch_catalog(self):
        return CatalogParseReport()

    def iter_images(self, characters, *, only_missing):
        return iter(())

    def check(self):
        return SourceCheckResult(ok=True, message="ok", checked_at=timezone.now())


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setitem(ADAPTERS, FakeAdapter.key, FakeAdapter)


@pytest.fixture
def enabled(settings):
    settings.EXTERNAL_IMPORT_ENABLED = True


def _login(client, user):
    client.force_login(user)
    return client


def test_painel_exibe_todas_as_fontes_inclusive_inelegiveis(client, adapter, enabled):
    admin = AdminUserFactory()
    eligible = CatalogSourceFactory(name="fonte-elegivel", adapter=FakeAdapter.key)
    disabled = CatalogSourceFactory(
        name="fonte-desabilitada", adapter=FakeAdapter.key, enabled=False
    )
    without_adapter = CatalogSourceFactory(name="fonte-sem-conector", adapter="")
    _login(client, admin)

    response = client.get(reverse("admin:catalog_status"))
    html = response.content.decode()

    assert response.status_code == 200
    assert eligible.name in html
    assert disabled.name in html
    assert without_adapter.name in html
    assert "Elegível" in html
    assert "Inelegível" in html
    assert reverse("admin:catalog_import") in html


def test_formulario_lista_somente_fontes_elegiveis(client, adapter, enabled):
    admin = AdminUserFactory()
    eligible = CatalogSourceFactory(name="fonte-elegivel", adapter=FakeAdapter.key)
    disabled = CatalogSourceFactory(
        name="fonte-desabilitada", adapter=FakeAdapter.key, enabled=False
    )
    without_adapter = CatalogSourceFactory(name="fonte-sem-conector", adapter="")
    _login(client, admin)

    response = client.get(reverse("admin:catalog_import"))
    html = response.content.decode()

    assert response.status_code == 200
    assert f'value="{eligible.pk}"' in html
    assert f'value="{disabled.pk}"' not in html
    assert f'value="{without_adapter.pk}"' not in html
    # O painel continua exibindo todas as fontes, com o motivo da inelegibilidade.
    assert disabled.name in html
    assert without_adapter.name in html


def test_post_cria_execucao_e_redireciona_para_detalhe(client, adapter, enabled, settings):
    settings.EXTERNAL_IMPORT_ENABLED = True
    admin = AdminUserFactory()
    source = CatalogSourceFactory(name="fonte-elegivel", adapter=FakeAdapter.key)
    _login(client, admin)

    response = client.post(
        reverse("admin:catalog_import"),
        {"source": source.pk, "kind": "catalog", "image_scope": "missing"},
    )

    job = ImportJob.objects.get(source=source)
    assert response.status_code == 302
    assert response["Location"] == reverse("admin:catalog_import_detail", args=[job.pk])
    assert job.status == ImportJob.Status.QUEUED
    assert job.triggered_by == admin


def test_detalhe_e_status_json(client, adapter, enabled):
    admin = AdminUserFactory()
    job = ImportJobFactory(
        source=CatalogSourceFactory(adapter=FakeAdapter.key),
        progress_total=10,
        progress_done=4,
    )
    _login(client, admin)

    detail = client.get(reverse("admin:catalog_import_detail", args=[job.pk]))
    status = client.get(reverse("admin:catalog_import_status", args=[job.pk]))

    assert detail.status_code == 200
    assert "Progresso" in detail.content.decode()
    assert status.status_code == 200
    assert status["Cache-Control"] == "no-store"
    payload = status.json()
    assert payload["id"] == job.pk
    assert payload["progress"] == {"done": 4, "total": 10, "percent": 40}
    assert payload["terminal"] is False


def test_cancelar_execucao_terminal_retorna_409(client, adapter, enabled):
    admin = AdminUserFactory()
    job = ImportJobFactory(
        source=CatalogSourceFactory(adapter=FakeAdapter.key),
        status=ImportJob.Status.SUCCESS,
        phase=ImportJob.Phase.FINISHED,
        finished_at=timezone.now(),
    )
    _login(client, admin)

    response = client.post(reverse("admin:catalog_import_cancel", args=[job.pk]))

    assert response.status_code == 409


def test_historico_lista_execucoes(client, adapter, enabled):
    admin = AdminUserFactory()
    job = ImportJobFactory(source=CatalogSourceFactory(adapter=FakeAdapter.key))
    _login(client, admin)

    response = client.get(reverse("admin:catalog_import_list"))
    html = response.content.decode()

    assert response.status_code == 200
    assert f"#{job.pk}" in html
