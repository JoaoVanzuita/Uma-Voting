"""Testes da fase de catálogo do worker de importação externa."""

from __future__ import annotations

import io

import pytest
from django.utils import timezone

from apps.catalog.models import Character, ImageAsset, ImportJob, SyncChange, SyncRun
from apps.catalog.services.importers import parse_catalog_csv
from apps.catalog.services.imports import request_cancel, run_import_job
from apps.catalog.services.sources.base import (
    ImageCandidate,
    ImageFetchError,
    SourceCheckResult,
    SourceDataError,
)
from apps.catalog.services.sources.registry import ADAPTERS
from tests.factories import (
    AdminUserFactory,
    CatalogSourceFactory,
    CharacterFactory,
    CharacterVersionFactory,
    ImageAssetFactory,
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


# ---------------------------------------------------------------------------
# Fase de imagens (T043)
# ---------------------------------------------------------------------------
def png_bytes(size=(256, 256), color=(20, 40, 60)) -> bytes:
    import io as _io

    from PIL import Image

    buffer = _io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def image_adapter_class(results, *, received=None):
    class _Adapter:
        key = "fake-source"
        display_name = "Fonte falsa"
        allowed_hosts = ()

        def __init__(self, source):
            self.source = source

        def fetch_catalog(self):
            raise AssertionError("fase de catálogo não deveria rodar")

        def iter_images(self, characters, *, only_missing):
            if received is not None:
                received.extend(characters)
            yield from results

        def check(self):
            return SourceCheckResult(True, "ok", timezone.now())

    return _Adapter


def images_job(source, *, scope="missing"):
    return ImportJobFactory(
        source=source,
        kind=ImportJob.Kind.IMAGES,
        status=ImportJob.Status.RUNNING,
        phase=ImportJob.Phase.IMAGES,
        options={"image_scope": scope},
        started_at=timezone.now(),
        heartbeat_at=timezone.now(),
    )


def test_fase_de_imagens_cria_assets(monkeypatch, source):
    character = CharacterFactory(stable_id="special-week", display_name="Special Week")
    register(
        monkeypatch,
        report=None,
    )
    monkeypatch.setitem(
        ADAPTERS,
        "fake-source",
        image_adapter_class(
            [
                ImageCandidate(
                    character_stable_id=character.stable_id,
                    data=png_bytes(),
                    source_url="https://example.com/special.png",
                )
            ]
        ),
    )
    job = images_job(source)

    result = run_import_job(job.pk, "worker-teste")

    result.refresh_from_db()
    assert result.status == ImportJob.Status.SUCCESS
    assert result.report["images"]["created"] == 1
    assert result.report["images"]["total"] == 1
    asset = ImageAsset.objects.get(character=character, is_current=True)
    assert asset.status == ImageAsset.Status.VALID
    assert asset.source == source


def test_fase_de_imagens_com_falha_isolada_e_parcial(monkeypatch, source):
    ok = CharacterFactory(stable_id="special-week", display_name="Special Week")
    failed = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    monkeypatch.setitem(
        ADAPTERS,
        "fake-source",
        image_adapter_class(
            [
                ImageCandidate(
                    character_stable_id=ok.stable_id,
                    data=png_bytes(),
                    source_url="https://example.com/ok.png",
                ),
                ImageFetchError(
                    character_stable_id=failed.stable_id,
                    source_url="https://example.com/404.png",
                    message="Resposta HTTP 404.",
                ),
            ]
        ),
    )
    job = images_job(source)

    result = run_import_job(job.pk, "worker-teste")

    assert result.status == ImportJob.Status.PARTIAL
    assert result.report["images"]["created"] == 1
    assert len(result.report["images"]["errors"]) == 1
    assert result.report["images"]["errors"][0]["character"] == "tokai-teio"
    assert ImageAsset.objects.filter(character=ok, is_current=True).exists()
    assert not ImageAsset.objects.filter(character=failed).exists()


def test_imagem_invalida_nao_impede_as_demais(monkeypatch, source):
    invalid = CharacterFactory(stable_id="special-week", display_name="Special Week")
    valid = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    monkeypatch.setitem(
        ADAPTERS,
        "fake-source",
        image_adapter_class(
            [
                ImageCandidate(
                    character_stable_id=invalid.stable_id,
                    data=b"nao-e-imagem",
                    source_url="https://example.com/invalid.png",
                ),
                ImageCandidate(
                    character_stable_id=valid.stable_id,
                    data=png_bytes(),
                    source_url="https://example.com/valid.png",
                ),
            ]
        ),
    )
    job = images_job(source)

    result = run_import_job(job.pk, "worker-teste")

    assert result.status == ImportJob.Status.PARTIAL
    assert result.report["images"]["created"] == 1
    assert len(result.report["images"]["errors"]) == 1
    assert ImageAsset.objects.filter(character=valid, is_current=True).exists()


def test_imagem_acima_do_limite_e_registrada(monkeypatch, source, settings):
    settings.EXTERNAL_IMPORT_MAX_IMAGE_BYTES = 100
    character = CharacterFactory(stable_id="special-week", display_name="Special Week")
    monkeypatch.setitem(
        ADAPTERS,
        "fake-source",
        image_adapter_class(
            [
                ImageCandidate(
                    character_stable_id=character.stable_id,
                    data=png_bytes(),
                    source_url="https://example.com/big.png",
                )
            ]
        ),
    )
    job = images_job(source)

    result = run_import_job(job.pk, "worker-teste")

    assert result.status == ImportJob.Status.PARTIAL
    assert "limite" in result.report["images"]["errors"][0]["message"]


def test_escopo_missing_nao_envia_personagem_com_imagem_valida(monkeypatch, source):
    with_image = CharacterFactory(stable_id="special-week", display_name="Special Week")
    without_image = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    ImageAssetFactory(character=with_image, is_current=True, status=ImageAsset.Status.VALID)
    received = []
    monkeypatch.setitem(
        ADAPTERS,
        "fake-source",
        image_adapter_class([], received=received),
    )
    job = images_job(source, scope="missing")

    result = run_import_job(job.pk, "worker-teste")

    assert result.status == ImportJob.Status.SUCCESS
    assert [character.pk for character in received] == [without_image.pk]
    assert result.report["images"]["total"] == 1


def test_modo_full_encadeia_catalogo_e_imagens(monkeypatch, source):
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    report = make_report(
        "tokai-teio,Tokai Teio,tokai-teio-original,Tokai Teio (Original),"
        "2025-06-26,pace,medium;long,turf\n"
    )

    class _Adapter:
        key = "fake-source"
        display_name = "Fonte falsa"
        allowed_hosts = ()

        def __init__(self, source):
            self.source = source

        def fetch_catalog(self):
            return report

        def iter_images(self, characters, *, only_missing):
            yield ImageCandidate(
                character_stable_id=character.stable_id,
                data=png_bytes(),
                source_url="https://example.com/full.png",
            )

        def check(self):
            return SourceCheckResult(True, "ok", timezone.now())

    monkeypatch.setitem(ADAPTERS, "fake-source", _Adapter)
    job = ImportJobFactory(
        source=source,
        kind=ImportJob.Kind.FULL,
        status=ImportJob.Status.RUNNING,
        phase=ImportJob.Phase.CATALOG,
        options={"image_scope": "missing"},
        started_at=timezone.now(),
        heartbeat_at=timezone.now(),
    )

    result = run_import_job(job.pk, "worker-teste")

    result.refresh_from_db()
    assert result.status == ImportJob.Status.SUCCESS
    assert result.report["catalog"]["new_versions"] == 1
    assert result.report["images"]["created"] == 1
    assert result.phase == ImportJob.Phase.FINISHED


def test_falha_no_catalogo_impede_fase_de_imagens(monkeypatch, source):
    called = {"images": False}

    class _Adapter:
        key = "fake-source"
        display_name = "Fonte falsa"
        allowed_hosts = ()

        def __init__(self, source):
            self.source = source

        def fetch_catalog(self):
            raise SourceDataError("lista oficial vazia")

        def iter_images(self, characters, *, only_missing):
            called["images"] = True
            yield ImageCandidate("x", png_bytes(), "https://example.com/x.png")

        def check(self):
            return SourceCheckResult(True, "ok", timezone.now())

    monkeypatch.setitem(ADAPTERS, "fake-source", _Adapter)
    job = ImportJobFactory(
        source=source,
        kind=ImportJob.Kind.FULL,
        status=ImportJob.Status.RUNNING,
        phase=ImportJob.Phase.CATALOG,
        started_at=timezone.now(),
        heartbeat_at=timezone.now(),
    )

    result = run_import_job(job.pk, "worker-teste")

    assert result.status == ImportJob.Status.FAILED
    assert called["images"] is False


def test_progresso_e_heartbeat_da_fase_de_imagens(monkeypatch, source):
    character = CharacterFactory(stable_id="special-week", display_name="Special Week")
    monkeypatch.setitem(
        ADAPTERS,
        "fake-source",
        image_adapter_class(
            [
                ImageCandidate(
                    character_stable_id=character.stable_id,
                    data=png_bytes(),
                    source_url="https://example.com/progress.png",
                )
            ]
        ),
    )
    job = images_job(source)
    job.heartbeat_at = None
    job.save(update_fields=["heartbeat_at"])

    result = run_import_job(job.pk, "worker-teste")

    result.refresh_from_db()
    assert result.progress_total == 1
    assert result.progress_done == 1
    assert result.heartbeat_at is not None


def test_worker_marca_execucao_stale_no_ciclo(monkeypatch):
    import json
    from datetime import timedelta
    from io import StringIO

    from django.core.management import call_command

    from apps.catalog.models import ImportJob

    source = CatalogSourceFactory(adapter="fake-source")
    stale = ImportJobFactory(
        source=source,
        status=ImportJob.Status.RUNNING,
        phase=ImportJob.Phase.IMAGES,
        heartbeat_at=timezone.now() - timedelta(seconds=1200),
    )
    output = StringIO()

    call_command("run_import_worker", "--once", "--json", stdout=output)

    payload = json.loads(output.getvalue())
    stale.refresh_from_db()
    assert payload["stale_jobs"] == 1
    assert stale.status == ImportJob.Status.FAILED
    assert stale.phase == ImportJob.Phase.FINISHED
    assert "sinal de vida" in stale.error_message
