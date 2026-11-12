"""Testes do ciclo de vida das execuções de importação externa."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import ImportJob
from apps.catalog.services.import_errors import (
    ImportDisabledError,
    ImportJobStateError,
    ImportSourceError,
)
from apps.catalog.services.importers import CatalogParseReport
from apps.catalog.services.imports import (
    claim_next_job,
    create_import_job,
    mark_stale_jobs,
    request_cancel,
    request_retry,
)
from apps.catalog.services.sources.base import SourceCheckResult
from apps.catalog.services.sources.registry import ADAPTERS
from tests.factories import AdminUserFactory, CatalogSourceFactory, ImportJobFactory


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
    return FakeAdapter


@pytest.fixture
def enabled(settings):
    settings.EXTERNAL_IMPORT_ENABLED = True


@pytest.mark.django_db
def test_cria_job_na_fila_com_opcoes_normalizadas(adapter, enabled):
    source = CatalogSourceFactory(adapter=FakeAdapter.key)
    admin = AdminUserFactory()

    job = create_import_job(
        source,
        ImportJob.Kind.FULL,
        options={"image_scope": "invalido"},
        triggered_by=admin,
    )

    assert job.status == ImportJob.Status.QUEUED
    assert job.phase == ImportJob.Phase.QUEUED
    assert job.options["image_scope"] == "missing"
    assert job.triggered_by == admin
    assert job.already_active is False


@pytest.mark.django_db
def test_nao_duplica_execucao_ativa_da_mesma_fonte(adapter, enabled):
    source = CatalogSourceFactory(adapter=FakeAdapter.key)

    first = create_import_job(source, ImportJob.Kind.CATALOG, triggered_by=None)
    second = create_import_job(source, ImportJob.Kind.CATALOG, triggered_by=None)

    assert second.pk == first.pk
    assert second.already_active is True
    assert ImportJob.objects.filter(source=source).count() == 1


@pytest.mark.django_db
def test_kill_switch_bloqueia_criacao(adapter, settings):
    settings.EXTERNAL_IMPORT_ENABLED = False
    source = CatalogSourceFactory(adapter=FakeAdapter.key)

    with pytest.raises(ImportDisabledError):
        create_import_job(source, ImportJob.Kind.CATALOG)


@pytest.mark.django_db
def test_fonte_desabilitada_ou_sem_conector_e_rejeitada(adapter, enabled):
    disabled = CatalogSourceFactory(adapter=FakeAdapter.key, enabled=False)
    without_adapter = CatalogSourceFactory(adapter="")

    with pytest.raises(ImportSourceError, match="desabilitada"):
        create_import_job(disabled, ImportJob.Kind.CATALOG)
    with pytest.raises(ImportSourceError, match="não possui conector"):
        create_import_job(without_adapter, ImportJob.Kind.CATALOG)


@pytest.mark.django_db
def test_importacao_de_imagens_nao_exige_nota_de_licenca(adapter, enabled):
    source = CatalogSourceFactory(adapter=FakeAdapter.key, license_note="")

    job = create_import_job(source, ImportJob.Kind.IMAGES)

    assert job.status == ImportJob.Status.QUEUED


@pytest.mark.django_db
def test_cancelamento_na_fila_marca_cancelada(adapter, enabled):
    source = CatalogSourceFactory(adapter=FakeAdapter.key)
    admin = AdminUserFactory()
    job = create_import_job(source, ImportJob.Kind.CATALOG, triggered_by=admin)

    cancelled = request_cancel(job, admin)

    cancelled.refresh_from_db()
    assert cancelled.status == ImportJob.Status.CANCELLED
    assert cancelled.phase == ImportJob.Phase.FINISHED
    assert cancelled.finished_at is not None
    assert cancelled.cancelled_by == admin
    assert cancelled.cancel_requested_at is not None


@pytest.mark.django_db
def test_cancelamento_em_execucao_apenas_solicita(adapter, enabled):
    source = CatalogSourceFactory(adapter=FakeAdapter.key)
    admin = AdminUserFactory()
    job = ImportJobFactory(source=source, status=ImportJob.Status.RUNNING, phase="catalog")

    request_cancel(job, admin)

    job.refresh_from_db()
    assert job.status == ImportJob.Status.RUNNING
    assert job.cancel_requested is True
    assert job.cancelled_by == admin


@pytest.mark.django_db
def test_cancelamento_de_execucao_terminal_falha(adapter, enabled):
    job = ImportJobFactory(
        source=CatalogSourceFactory(adapter=FakeAdapter.key),
        status=ImportJob.Status.SUCCESS,
        phase=ImportJob.Phase.FINISHED,
        finished_at=timezone.now(),
    )

    with pytest.raises(ImportJobStateError):
        request_cancel(job, AdminUserFactory())


@pytest.mark.django_db
def test_repeticao_cria_novo_job_vinculado(adapter, enabled):
    source = CatalogSourceFactory(adapter=FakeAdapter.key)
    admin = AdminUserFactory()
    original = ImportJobFactory(
        source=source,
        status=ImportJob.Status.FAILED,
        phase=ImportJob.Phase.FINISHED,
        finished_at=timezone.now(),
        error_message="falha",
        attempts=1,
    )

    new_job = request_retry(original, admin)

    assert new_job.pk != original.pk
    assert new_job.retry_of == original
    assert new_job.attempts == 0
    assert new_job.status == ImportJob.Status.QUEUED


@pytest.mark.django_db
def test_repeticao_de_execucao_ativa_falha(adapter, enabled):
    job = ImportJobFactory(
        source=CatalogSourceFactory(adapter=FakeAdapter.key),
        status=ImportJob.Status.RUNNING,
        phase="catalog",
    )

    with pytest.raises(ImportJobStateError):
        request_retry(job, AdminUserFactory())


@pytest.mark.django_db
def test_stale_marca_falha_sem_sinal_de_vida(adapter, enabled):
    source = CatalogSourceFactory(adapter=FakeAdapter.key)
    old = ImportJobFactory(
        source=source,
        status=ImportJob.Status.RUNNING,
        phase="images",
        heartbeat_at=timezone.now() - timedelta(seconds=1200),
    )

    affected = mark_stale_jobs(threshold=600)

    old.refresh_from_db()
    assert affected == 1
    assert old.status == ImportJob.Status.FAILED
    assert old.phase == ImportJob.Phase.FINISHED
    assert "sinal de vida" in old.error_message


@pytest.mark.django_db
def test_claim_define_execucao_e_fase(adapter, enabled):
    source = CatalogSourceFactory(adapter=FakeAdapter.key)
    job = ImportJobFactory(source=source, kind=ImportJob.Kind.FULL)

    claimed = claim_next_job("worker-teste")

    assert claimed.pk == job.pk
    claimed.refresh_from_db()
    assert claimed.status == ImportJob.Status.RUNNING
    assert claimed.phase == ImportJob.Phase.CATALOG
    assert claimed.started_at is not None
    assert claimed.heartbeat_at is not None
    assert claimed.attempts == 1
    assert claim_next_job("worker-teste") is None


@pytest.mark.django_db
def test_worker_once_sem_jobs_emite_json(adapter, enabled):
    import json
    from io import StringIO

    from django.core.management import call_command

    output = StringIO()

    call_command("run_import_worker", "--once", "--json", stdout=output)

    payload = json.loads(output.getvalue())
    assert payload["processed"] == []
    assert payload["stale_jobs"] == 0


@pytest.mark.django_db
def test_repeticao_de_sucesso_e_bloqueada(adapter, enabled):
    job = ImportJobFactory(
        source=CatalogSourceFactory(adapter=FakeAdapter.key),
        status=ImportJob.Status.SUCCESS,
        phase=ImportJob.Phase.FINISHED,
        finished_at=timezone.now(),
    )

    with pytest.raises(ImportJobStateError, match="parciais|falha|canceladas"):
        request_retry(job, AdminUserFactory())


@pytest.mark.django_db
def test_repeticao_nao_altera_execucao_original(adapter, enabled):
    original = ImportJobFactory(
        source=CatalogSourceFactory(adapter=FakeAdapter.key),
        status=ImportJob.Status.FAILED,
        phase=ImportJob.Phase.FINISHED,
        finished_at=timezone.now(),
        error_message="falha original",
        attempts=2,
    )

    request_retry(original, AdminUserFactory())

    original.refresh_from_db()
    assert original.status == ImportJob.Status.FAILED
    assert original.error_message == "falha original"
    assert original.attempts == 2
