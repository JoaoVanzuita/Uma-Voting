"""Testes da fase de catálogo do worker de importação externa."""

from __future__ import annotations

import io

import pytest
from django.utils import timezone

from apps.catalog.models import Character, ImportJob, SyncChange, SyncRun
from apps.catalog.services.importers import parse_catalog_csv
from apps.catalog.services.imports import request_cancel, run_import_job
from apps.catalog.services.sources.base import SourceCheckResult, SourceDataError
from apps.catalog.services.sources.registry import ADAPTERS
from tests.factories import (
    AdminUserFactory,
    CatalogSourceFactory,
    CharacterFactory,
    CharacterVersionFactory,
    ImportJobFactory,
)

pytestmark = pytest.mark.django_db

HEADER = (
    "character_stable_id,character_name,version_stable_id,version_name,"
    "release_date_global,strategy,distances,surfaces\n"
)


def make_report(body: str):
    return parse_catalog_csv(io.BytesIO((HEADER + body).encode("utf-8")))


def adapter_class(*, report=None, error: Exception | None = None):
    class _Adapter:
        key = "fake-source"
        display_name = "Fonte falsa"
        allowed_hosts = ()

        def __init__(self, source):
            self.source = source

        def fetch_catalog(self):
            if error is not None:
                raise error
            return report

        def iter_images(self, characters, *, only_missing):
            return iter(())

        def check(self):
            return SourceCheckResult(True, "ok", timezone.now())

    return _Adapter


@pytest.fixture
def source():
    return CatalogSourceFactory(name="fonte-teste", adapter="fake-source")


def register(monkeypatch, *, report=None, error=None):
    monkeypatch.setitem(ADAPTERS, "fake-source", adapter_class(report=report, error=error))


def running_job(source):
    return ImportJobFactory(
        source=source,
        kind=ImportJob.Kind.CATALOG,
        status=ImportJob.Status.RUNNING,
        phase=ImportJob.Phase.CATALOG,
        started_at=timezone.now(),
        heartbeat_at=timezone.now(),
    )


def test_catalogo_aplicado_automaticamente(monkeypatch, source):
    report = make_report(
        "tokai-teio,Tokai Teio,tokai-teio-original,Tokai Teio (Original),"
        "2025-06-26,pace,medium;long,turf\n"
    )
    register(monkeypatch, report=report)
    job = running_job(source)

    result = run_import_job(job.pk, "worker-teste")

    result.refresh_from_db()
    assert result.status == ImportJob.Status.SUCCESS
    assert result.phase == ImportJob.Phase.FINISHED
    assert result.finished_at is not None
    assert result.sync_run is not None
    assert result.sync_run.origin == SyncRun.Origin.EXTERNAL
    assert result.sync_run.status == SyncRun.Status.SUCCESS
    assert not result.sync_run.changes.filter(status=SyncChange.Status.PENDING).exists()
    assert result.sync_run.changes.filter(status=SyncChange.Status.AUTO_APPLIED).count() == 1
    assert result.report["catalog"]["new_characters"] == 1
    assert result.report["catalog"]["total_rows"] == 1
    assert Character.objects.filter(stable_id="tokai-teio").exists()


def test_lista_vazia_falha_sem_gravar(monkeypatch, source):
    register(monkeypatch, error=SourceDataError("A lista oficial não retornou personagens."))
    job = running_job(source)

    result = run_import_job(job.pk, "worker-teste")

    result.refresh_from_db()
    assert result.status == ImportJob.Status.FAILED
    assert "lista oficial" in result.error_message
    assert Character.objects.count() == 0


def test_gametora_indisponivel_falha(monkeypatch, source):
    from apps.catalog.services.sources.base import SourceUnavailableError

    register(monkeypatch, error=SourceUnavailableError("GameTora indisponível."))
    job = running_job(source)

    result = run_import_job(job.pk, "worker-teste")

    assert result.status == ImportJob.Status.FAILED
    assert "GameTora" in result.error_message


def test_conflito_de_versao_aborta_aplicacao(monkeypatch, source):
    other = CharacterFactory(stable_id="outra-personagem")
    CharacterVersionFactory(stable_id="tokai-teio-original", character=other)
    report = make_report(
        "tokai-teio,Tokai Teio,tokai-teio-original,Tokai Teio (Original),"
        "2025-06-26,pace,medium;long,turf\n"
    )
    register(monkeypatch, report=report)
    job = running_job(source)

    result = run_import_job(job.pk, "worker-teste")

    assert result.status == ImportJob.Status.FAILED
    assert "outra personagem" in result.error_message
    assert not Character.objects.filter(stable_id="tokai-teio").exists()
    failed_run = SyncRun.objects.get(source=source)
    assert failed_run.status == SyncRun.Status.FAILED


def test_identificador_duplicado_falha(monkeypatch, source):
    register(monkeypatch, error=SourceDataError("mesmo identificador 'special-week'"))
    job = running_job(source)

    result = run_import_job(job.pk, "worker-teste")

    assert result.status == ImportJob.Status.FAILED
    assert "mesmo identificador" in result.error_message


def test_detalhe_404_e_aviso_e_nao_falha(monkeypatch, source):
    report = make_report(
        "tokai-teio,Tokai Teio,tokai-teio-original,Tokai Teio (Original),"
        "2025-06-26,pace,medium;long,turf\n"
    )
    report.warnings.append("Detalhe oficial ausente para 'silence-suzuka' (HTTP 404).")
    register(monkeypatch, report=report)
    job = running_job(source)

    result = run_import_job(job.pk, "worker-teste")

    assert result.status == ImportJob.Status.SUCCESS
    assert any("404" in warning for warning in result.report["catalog"]["warnings"])


def test_cancelamento_antes_da_aplicacao_nao_grava(monkeypatch, source):
    report = make_report(
        "tokai-teio,Tokai Teio,tokai-teio-original,Tokai Teio (Original),"
        "2025-06-26,pace,medium;long,turf\n"
    )
    register(monkeypatch, report=report)
    job = running_job(source)
    admin = AdminUserFactory()
    request_cancel(job, admin)

    result = run_import_job(job.pk, "worker-teste")

    result.refresh_from_db()
    assert result.status == ImportJob.Status.CANCELLED
    assert Character.objects.count() == 0
    assert not SyncRun.objects.filter(source=source).exists()
