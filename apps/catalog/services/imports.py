"""Fila e execução da importação externa de catálogo e imagens."""

from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.catalog.models import CatalogSource, Character, ImageAsset, ImportJob, SyncRun
from apps.catalog.services.images import store_image_bytes
from apps.catalog.services.import_errors import (
    ImportDisabledError,
    ImportJobError,
    ImportJobStateError,
    ImportSourceError,
)
from apps.catalog.services.sources.base import (
    ImageCandidate,
    ImageFetchError,
    SourceError,
)
from apps.catalog.services.sources.registry import get_adapter, is_supported
from apps.catalog.services.sync import sync_from_report

logger = logging.getLogger("apps.catalog.imports")

IMAGE_KINDS = {ImportJob.Kind.IMAGES, ImportJob.Kind.FULL}
CATALOG_KINDS = {ImportJob.Kind.CATALOG, ImportJob.Kind.FULL}


# ---------------------------------------------------------------------------
# Criação e operação de execuções
# ---------------------------------------------------------------------------
def create_import_job(
    source: CatalogSource,
    kind: str,
    *,
    options: dict | None = None,
    triggered_by=None,
) -> ImportJob:
    """Valida a fonte e cria (ou reutiliza) uma execução na fila."""
    if not settings.EXTERNAL_IMPORT_ENABLED:
        raise ImportDisabledError("Importação externa desabilitada.")
    if kind not in ImportJob.Kind.values:
        raise ImportJobError("Tipo de importação inválido.")
    if not source.enabled:
        raise ImportSourceError(f"A fonte '{source.name}' está desabilitada.")
    if not is_supported(source):
        raise ImportSourceError(
            f"A fonte '{source.name}' não possui conector de importação externa."
        )

    normalized_options = dict(options or {})
    scope = normalized_options.get("image_scope", "missing")
    normalized_options["image_scope"] = scope if scope in {"missing", "all"} else "missing"

    with transaction.atomic():
        existing = (
            ImportJob.objects.select_for_update()
            .filter(
                source=source,
                status__in=[ImportJob.Status.QUEUED, ImportJob.Status.RUNNING],
            )
            .order_by("-created_at")
            .first()
        )
        if existing is not None:
            logger.info(
                "import_job.reused job_id=%s source=%s status=%s",
                existing.pk,
                source.name,
                existing.status,
            )
            existing.already_active = True
            return existing

        job = ImportJob.objects.create(
            source=source,
            kind=kind,
            status=ImportJob.Status.QUEUED,
            phase=ImportJob.Phase.QUEUED,
            options=normalized_options,
            triggered_by=triggered_by,
        )

    logger.info(
        "import_job.created job_id=%s source=%s kind=%s",
        job.pk,
        source.name,
        kind,
    )
    job.already_active = False
    return job


def request_cancel(job: ImportJob, admin) -> ImportJob:
    """Cancela uma execução na fila ou solicita o cancelamento de uma ativa."""
    now = timezone.now()
    with transaction.atomic():
        locked = ImportJob.objects.select_for_update().get(pk=job.pk)
        if locked.is_terminal:
            raise ImportJobStateError("Execução já encerrada.")

        if locked.status == ImportJob.Status.QUEUED:
            locked.status = ImportJob.Status.CANCELLED
            locked.phase = ImportJob.Phase.FINISHED
            locked.finished_at = now
            locked.cancel_requested = True
            locked.cancelled_by = admin
            locked.cancel_requested_at = now
            locked.current_step = "Cancelada antes de iniciar"
            locked.save(
                update_fields=[
                    "status",
                    "phase",
                    "finished_at",
                    "cancel_requested",
                    "cancelled_by",
                    "cancel_requested_at",
                    "current_step",
                ]
            )
        else:
            # A execução em curso encerra no próximo ponto seguro.
            locked.cancel_requested = True
            locked.cancelled_by = admin
            locked.cancel_requested_at = now
            locked.current_step = "Cancelamento solicitado"
            locked.save(
                update_fields=[
                    "cancel_requested",
                    "cancelled_by",
                    "cancel_requested_at",
                    "current_step",
                ]
            )

    if locked.status == ImportJob.Status.CANCELLED:
        logger.info("import_job.cancelled job_id=%s source=%s", locked.pk, locked.source.name)
    else:
        logger.info(
            "import_job.cancel_requested job_id=%s source=%s phase=%s",
            locked.pk,
            locked.source.name,
            locked.phase,
        )
    return locked


def request_retry(job: ImportJob, admin) -> ImportJob:
    """Cria uma nova execução com os mesmos parâmetros de uma execução terminal."""
    if job.status not in {
        ImportJob.Status.PARTIAL,
        ImportJob.Status.FAILED,
        ImportJob.Status.CANCELLED,
    }:
        raise ImportJobStateError(
            "Somente execuções parciais, com falha ou canceladas podem ser repetidas."
        )

    new_job = create_import_job(
        job.source,
        job.kind,
        options=job.options,
        triggered_by=admin,
    )
    if getattr(new_job, "already_active", False):
        return new_job

    new_job.retry_of = job
    new_job.attempts = 0
    new_job.save(update_fields=["retry_of", "attempts"])
    logger.info(
        "import_job.retry_requested job_id=%s retry_of=%s",
        new_job.pk,
        job.pk,
    )
    return new_job


def mark_stale_jobs(now=None, threshold: int | None = None) -> int:
    """Marca como falha execuções ``running`` sem sinal de vida recente."""
    now = now or timezone.now()
    threshold = settings.EXTERNAL_IMPORT_STALE_SECONDS if threshold is None else threshold
    cutoff = now - timedelta(seconds=threshold)

    stale = ImportJob.objects.filter(status=ImportJob.Status.RUNNING).filter(
        Q(heartbeat_at__isnull=True) | Q(heartbeat_at__lt=cutoff)
    )

    affected = 0
    for job in stale.only("pk"):
        updated = ImportJob.objects.filter(
            pk=job.pk,
            status=ImportJob.Status.RUNNING,
        ).update(
            status=ImportJob.Status.FAILED,
            phase=ImportJob.Phase.FINISHED,
            finished_at=now,
            error_message="Execução interrompida sem sinal de vida.",
            current_step="Execução interrompida",
        )
        if updated:
            affected += 1
            logger.warning("import_job.stale job_id=%s", job.pk)

    return affected


def last_failure_for_source(source: CatalogSource) -> ImportJob | None:
    """Última execução com falha da fonte, para o painel de diagnóstico."""
    return (
        ImportJob.objects.filter(source=source, status=ImportJob.Status.FAILED)
        .order_by("-finished_at", "-created_at")
        .first()
    )


def check_source(source: CatalogSource):
    """Verifica disponibilidade sem criar job nem gravar catálogo/imagens."""
    if not is_supported(source):
        raise ImportSourceError(
            f"A fonte '{source.name}' não possui conector de importação externa."
        )
    adapter = get_adapter(source, require_enabled=False)
    return adapter.check()


def claim_next_job(worker_id: str) -> ImportJob | None:
    """Reivindica o job ``queued`` mais antigo; requer advisory lock do worker."""
    now = timezone.now()
    with transaction.atomic():
        job = (
            ImportJob.objects.select_for_update(skip_locked=True)
            .filter(status=ImportJob.Status.QUEUED)
            .select_related("source")
            .order_by("created_at", "pk")
            .first()
        )
        if job is None:
            return None

        job.status = ImportJob.Status.RUNNING
        job.phase = ImportJob.Phase.CATALOG if job.kind in CATALOG_KINDS else ImportJob.Phase.IMAGES
        job.started_at = now
        job.heartbeat_at = now
        job.attempts += 1
        job.current_step = "Iniciando importação"
        job.save(
            update_fields=[
                "status",
                "phase",
                "started_at",
                "heartbeat_at",
                "attempts",
                "current_step",
            ]
        )

    logger.info(
        "import_job.claimed job_id=%s source=%s kind=%s phase=%s status=%s worker=%s",
        job.pk,
        job.source.name,
        job.kind,
        job.phase,
        job.status,
        worker_id,
    )
    return job


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------
def _touch(job: ImportJob, *, step: str | None = None, **fields) -> None:
    job.heartbeat_at = timezone.now()
    update_fields = ["heartbeat_at"]
    if step is not None:
        job.current_step = step
        update_fields.append("current_step")
    for name, value in fields.items():
        setattr(job, name, value)
        update_fields.append(name)
    job.save(update_fields=update_fields)


def _finish(
    job: ImportJob,
    status: str,
    *,
    error_message: str = "",
) -> ImportJob:
    job.refresh_from_db()
    job.status = status
    job.phase = ImportJob.Phase.FINISHED
    job.finished_at = timezone.now()
    job.error_message = error_message
    job.heartbeat_at = job.finished_at
    job.save(
        update_fields=[
            "status",
            "phase",
            "finished_at",
            "error_message",
            "heartbeat_at",
            "report",
        ]
    )
    duration_ms = None
    if job.started_at is not None:
        duration_ms = int((job.finished_at - job.started_at).total_seconds() * 1000)
    logger.info(
        "import_job.completed job_id=%s source=%s status=%s phase=%s "
        "progress_done=%s progress_total=%s duration_ms=%s error=%s",
        job.pk,
        job.source.name,
        status,
        job.phase,
        job.progress_done,
        job.progress_total,
        duration_ms,
        error_message[:200],
    )
    return job


def run_catalog_phase(job: ImportJob, adapter) -> SyncRun | None:
    """Coleta e aplica o catálogo externo em uma única transação."""
    _touch(job, step="Coletando catálogo", phase=ImportJob.Phase.CATALOG)
    logger.info("import_job.phase.started job_id=%s phase=catalog", job.pk)

    report = adapter.fetch_catalog()
    catalog_report = {
        "total_rows": report.total_rows,
        "characters": len(report.characters),
        "new_characters": 0,
        "updated_characters": 0,
        "new_versions": 0,
        "updated_versions": 0,
        "aptitude_changes": 0,
        "ignored": len(report.ignored_characters),
        "warnings": list(report.warnings),
        "errors": report.error_dicts(),
    }
    job.report = {**(job.report or {}), "catalog": catalog_report}
    _touch(job, report=job.report)

    if report.has_errors:
        raise ImportJobError("; ".join(issue.message for issue in report.errors))

    job.refresh_from_db(fields=["cancel_requested"])
    if job.cancel_requested:
        _touch(job, current_step="Cancelamento solicitado")
        return None

    sync_run = sync_from_report(
        report,
        job.source,
        triggered_by=job.triggered_by,
        apply_all=True,
        origin=SyncRun.Origin.EXTERNAL,
    )

    if sync_run.status == SyncRun.Status.FAILED:
        _touch(job, report=job.report)
        raise ImportJobError(sync_run.error_message or "Falha ao aplicar o catálogo.")

    counts = {
        row["change_type"]: row["total"]
        for row in sync_run.changes.values("change_type").annotate(total=Count("id"))
    }
    catalog_report.update(
        {
            "new_characters": counts.get("new_character", 0),
            "updated_characters": counts.get("update_character", 0),
            "new_versions": counts.get("new_version", 0),
            "updated_versions": counts.get("update_version", 0),
            "aptitude_changes": counts.get("aptitude_change", 0),
        }
    )
    job.report = {**(job.report or {}), "catalog": catalog_report, "sync_run_id": sync_run.pk}
    job.sync_run = sync_run
    _touch(
        job,
        report=job.report,
        sync_run=sync_run,
        progress_total=len(report.characters),
        progress_done=len(report.characters),
        phase=ImportJob.Phase.IMAGES
        if job.kind == ImportJob.Kind.FULL
        else ImportJob.Phase.CATALOG,
    )
    logger.info("import_job.phase.finished job_id=%s phase=catalog", job.pk)
    return sync_run


def _characters_for_scope(scope: str) -> list[Character]:
    characters = Character.objects.all().order_by("display_name")
    if scope == "all":
        return list(characters)
    valid_ids = ImageAsset.objects.filter(
        is_current=True,
        status=ImageAsset.Status.VALID,
    ).values_list("character_id", flat=True)
    return list(characters.exclude(pk__in=valid_ids))


def run_images_phase(job: ImportJob, adapter) -> None:
    """Baixa e grava imagens, acumulando falhas isoladas no relatório."""
    scope = (job.options or {}).get("image_scope", "missing")
    characters = _characters_for_scope(scope)
    total = len(characters)
    _touch(
        job,
        step="Preparando imagens",
        phase=ImportJob.Phase.IMAGES,
        progress_total=total,
        progress_done=0,
    )
    logger.info("import_job.phase.started job_id=%s phase=images total=%s", job.pk, total)

    images_report = {
        "total": total,
        "created": 0,
        "replaced": 0,
        "reused": 0,
        "skipped": 0,
        "warnings": [],
        "errors": [],
    }

    by_stable_id = {character.stable_id: character for character in characters}
    done = 0
    cancelled = False

    for item in adapter.iter_images(characters, only_missing=scope == "missing"):
        job.refresh_from_db(fields=["cancel_requested"])
        if job.cancel_requested:
            cancelled = True
            break

        done += 1
        if isinstance(item, ImageFetchError):
            images_report["errors"].append(
                {
                    "character": item.character_stable_id,
                    "url": item.source_url,
                    "message": item.message,
                }
            )
            _touch(job, progress_done=done, step=f"Falha em {item.character_stable_id}")
            continue

        if not isinstance(item, ImageCandidate):
            continue

        character = by_stable_id.get(item.character_stable_id)
        if character is None:
            images_report["errors"].append(
                {
                    "character": item.character_stable_id,
                    "url": item.source_url,
                    "message": "Personagem não encontrada no catálogo local.",
                }
            )
            _touch(job, progress_done=done)
            continue

        _touch(job, step=f"Baixando imagem de {character.display_name}")
        try:
            result = store_image_bytes(
                character,
                item.data,
                source=job.source,
                source_url=item.source_url,
                license_note=job.source.license_note,
                is_current=True,
                max_bytes=settings.EXTERNAL_IMPORT_MAX_IMAGE_BYTES,
                require_license=False,
            )
        except (OSError, ValueError) as exc:
            images_report["errors"].append(
                {
                    "character": item.character_stable_id,
                    "url": item.source_url,
                    "message": str(exc),
                }
            )
        else:
            if result.action == "create":
                images_report["created"] += 1
            elif result.action == "replace":
                images_report["replaced"] += 1
            else:
                images_report["reused"] += 1
            images_report["warnings"].extend(result.warnings)

        _touch(job, progress_done=done)

    job.refresh_from_db()
    images_report["skipped"] = max(0, total - done)
    job.report = {**(job.report or {}), "images": images_report}
    job.save(update_fields=["report"])
    logger.info(
        "import_job.phase.finished job_id=%s phase=images errors=%s cancelled=%s",
        job.pk,
        len(images_report["errors"]),
        cancelled,
    )


def run_import_job(job_id: int, worker_id: str) -> ImportJob:
    """Executa as fases previstas para o job e consolida o status final."""
    job = ImportJob.objects.select_related("source").get(pk=job_id)
    logger.info(
        "import_job.started job_id=%s source=%s kind=%s worker=%s",
        job.pk,
        job.source.name,
        job.kind,
        worker_id,
    )

    try:
        adapter = get_adapter(job.source)
    except ImportJobError as exc:
        return _finish(job, ImportJob.Status.FAILED, error_message=str(exc))

    try:
        if job.kind in CATALOG_KINDS:
            run_catalog_phase(job, adapter)

        job.refresh_from_db()
        if (
            job.kind in IMAGE_KINDS
            and not job.cancel_requested
            and job.status == ImportJob.Status.RUNNING
        ):
            run_images_phase(job, adapter)
    except SourceError as exc:
        return _finish(job, ImportJob.Status.FAILED, error_message=str(exc))
    except ImportJobError as exc:
        return _finish(job, ImportJob.Status.FAILED, error_message=str(exc))
    except Exception as exc:  # pragma: no cover - proteção do worker
        logger.exception("import_job.unexpected_error job_id=%s", job.pk)
        return _finish(job, ImportJob.Status.FAILED, error_message=f"Erro inesperado: {exc}")

    job.refresh_from_db()
    if job.cancel_requested and job.cancelled_by_id is not None:
        return _finish(job, ImportJob.Status.CANCELLED)

    images_report = (job.report or {}).get("images") or {}
    if images_report.get("errors"):
        return _finish(
            job,
            ImportJob.Status.PARTIAL,
            error_message=f"{len(images_report['errors'])} imagem(ns) com falha.",
        )

    return _finish(job, ImportJob.Status.SUCCESS)
