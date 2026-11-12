"""Smoke tests das telas administrativas de importação externa."""

from __future__ import annotations

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import ImportJob, SyncRun
from apps.catalog.services.importers import CatalogParseReport
from apps.catalog.services.sources.base import SourceCheckResult
from apps.catalog.services.sources.registry import ADAPTERS
from tests.factories import (
    AdminUserFactory,
    CatalogSourceFactory,
    ImportJobFactory,
    ParticipantFactory,
)

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


# ---------------------------------------------------------------------------
# Criação, detalhe e proteções (T031/T032)
# ---------------------------------------------------------------------------
def test_post_redireciona_para_execucao_ativa_existente(client, adapter, enabled):
    admin = AdminUserFactory()
    source = CatalogSourceFactory(name="fonte-elegivel", adapter=FakeAdapter.key)
    active = ImportJobFactory(source=source, status=ImportJob.Status.QUEUED)
    _login(client, admin)

    response = client.post(
        reverse("admin:catalog_import"),
        {"source": source.pk, "kind": "catalog", "image_scope": "missing"},
        follow=True,
    )

    assert response.status_code == 200
    assert ImportJob.objects.filter(source=source).count() == 1
    assert reverse("admin:catalog_import_detail", args=[active.pk]) in [
        url for url, _status in response.redirect_chain
    ]
    assert any("execução ativa" in str(message) for message in response.context["messages"])


def test_kill_switch_impede_criacao_pela_view(client, adapter, settings):
    settings.EXTERNAL_IMPORT_ENABLED = False
    admin = AdminUserFactory()
    source = CatalogSourceFactory(name="fonte-elegivel", adapter=FakeAdapter.key)
    _login(client, admin)

    response = client.post(
        reverse("admin:catalog_import"),
        {"source": source.pk, "kind": "catalog", "image_scope": "missing"},
    )

    assert response.status_code == 200
    assert "Importação externa desabilitada" in response.content.decode()
    assert not ImportJob.objects.filter(source=source).exists()


def test_fonte_desabilitada_nao_pode_ser_enviada(client, adapter, enabled):
    admin = AdminUserFactory()
    source = CatalogSourceFactory(name="fonte-desabilitada", adapter=FakeAdapter.key, enabled=False)
    _login(client, admin)

    response = client.post(
        reverse("admin:catalog_import"),
        {"source": source.pk, "kind": "catalog", "image_scope": "missing"},
    )

    assert response.status_code == 200
    assert not ImportJob.objects.filter(source=source).exists()


def test_fonte_sem_conector_nao_pode_ser_enviada(client, adapter, enabled):
    admin = AdminUserFactory()
    source = CatalogSourceFactory(name="fonte-sem-conector", adapter="")
    _login(client, admin)

    response = client.post(
        reverse("admin:catalog_import"),
        {"source": source.pk, "kind": "catalog", "image_scope": "missing"},
    )

    assert response.status_code == 200
    assert not ImportJob.objects.filter(source=source).exists()


def test_importacao_de_imagens_exige_confirmacao_de_licenca(client, adapter, enabled):
    admin = AdminUserFactory()
    source = CatalogSourceFactory(
        name="fonte-elegivel", adapter=FakeAdapter.key, license_note="Uso interno."
    )
    _login(client, admin)

    response = client.post(
        reverse("admin:catalog_import"),
        {"source": source.pk, "kind": "images", "image_scope": "missing"},
    )

    assert response.status_code == 200
    assert "Confirme a leitura da nota de licença" in response.content.decode()
    assert not ImportJob.objects.filter(source=source).exists()


def test_usuario_nao_administrador_recebe_403(client, adapter, enabled):
    source = CatalogSourceFactory(adapter=FakeAdapter.key)
    client.force_login(ParticipantFactory())

    response = client.get(reverse("admin:catalog_import"))

    assert response.status_code == 403
    assert source.name not in response.content.decode()


def test_post_exige_csrf(client, adapter, enabled):
    admin = AdminUserFactory()
    source = CatalogSourceFactory(adapter=FakeAdapter.key)
    client.force_login(admin)
    csrf_client = Client(enforce_csrf_checks=True)
    csrf_client.force_login(admin)

    response = csrf_client.post(
        reverse("admin:catalog_import"),
        {"source": source.pk, "kind": "catalog", "image_scope": "missing"},
    )

    assert response.status_code == 403
    assert not ImportJob.objects.filter(source=source).exists()


def test_detalhe_exibe_relatorio_vinculo_e_ultima_falha(client, adapter, enabled):
    admin = AdminUserFactory()
    source = CatalogSourceFactory(adapter=FakeAdapter.key)
    sync_run = SyncRun.objects.create(
        source=source,
        status=SyncRun.Status.SUCCESS,
        origin=SyncRun.Origin.EXTERNAL,
        finished_at=timezone.now(),
    )
    failure = ImportJobFactory(
        source=source,
        status=ImportJob.Status.FAILED,
        phase=ImportJob.Phase.FINISHED,
        finished_at=timezone.now(),
        error_message="GameTora indisponível.",
    )
    job = ImportJobFactory(
        source=source,
        status=ImportJob.Status.SUCCESS,
        phase=ImportJob.Phase.FINISHED,
        finished_at=timezone.now(),
        sync_run=sync_run,
        report={
            "catalog": {
                "total_rows": 3,
                "new_characters": 1,
                "warnings": ["Detalhe ausente (HTTP 404)."],
            },
            "images": {
                "total": 1,
                "created": 0,
                "errors": [
                    {
                        "character": "special-week",
                        "url": "https://example.com/404.png",
                        "message": "Resposta HTTP 404.",
                    }
                ],
            },
        },
    )
    _login(client, admin)

    response = client.get(reverse("admin:catalog_import_detail", args=[job.pk]))
    html = response.content.decode()

    assert response.status_code == 200
    assert "Relatório de catálogo" in html
    assert "Novas personagens" in html
    assert "Detalhe ausente (HTTP 404)." in html
    assert reverse("admin:catalog_sync_detail", args=[sync_run.pk]) in html
    assert reverse("admin:catalog_import_detail", args=[failure.pk]) in html
    assert "GameTora indisponível." in html
    assert "Relatório de imagens" in html
    assert reverse("admin:catalog_images_validate") in html
    assert "Resposta HTTP 404." in html


# ---------------------------------------------------------------------------
# Escopo das imagens no formulário (T045)
# ---------------------------------------------------------------------------
def test_formulario_tem_escopo_padrao_missing(client, adapter, enabled):
    admin = AdminUserFactory()
    CatalogSourceFactory(adapter=FakeAdapter.key)
    _login(client, admin)

    response = client.get(reverse("admin:catalog_import"))
    html = response.content.decode()

    assert 'value="missing" selected' in html
    assert "Somente personagens sem imagem válida" in html
    assert 'value="all"' in html


def test_escopo_omitido_vira_missing(client, adapter, enabled):
    admin = AdminUserFactory()
    source = CatalogSourceFactory(adapter=FakeAdapter.key, license_note="Uso interno.")
    _login(client, admin)

    client.post(
        reverse("admin:catalog_import"),
        {"source": source.pk, "kind": "images", "license_ack": "on"},
    )

    job = ImportJob.objects.get(source=source)
    assert job.options["image_scope"] == "missing"


def test_escopo_all_e_persistido(client, adapter, enabled):
    admin = AdminUserFactory()
    source = CatalogSourceFactory(adapter=FakeAdapter.key, license_note="Uso interno.")
    _login(client, admin)

    client.post(
        reverse("admin:catalog_import"),
        {
            "source": source.pk,
            "kind": "full",
            "image_scope": "all",
            "license_ack": "on",
        },
    )

    job = ImportJob.objects.get(source=source)
    assert job.kind == ImportJob.Kind.FULL
    assert job.options["image_scope"] == "all"


def test_escopo_invalido_e_normalizado_para_missing(client, adapter, enabled):
    admin = AdminUserFactory()
    source = CatalogSourceFactory(adapter=FakeAdapter.key)
    _login(client, admin)

    client.post(
        reverse("admin:catalog_import"),
        {"source": source.pk, "kind": "catalog", "image_scope": "invalido"},
    )

    job = ImportJob.objects.get(source=source)
    assert job.options["image_scope"] == "missing"
