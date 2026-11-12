"""Views administrativas do catálogo e das imagens."""

from __future__ import annotations

import os
import tempfile
from datetime import date

from django.conf import settings
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from apps.catalog.forms import CatalogSyncForm, ImportJobForm
from apps.catalog.models import (
    CatalogSource,
    Character,
    ImageAsset,
    ImportJob,
    SyncChange,
    SyncRun,
)
from apps.catalog.services.images import validate_all_images
from apps.catalog.services.import_errors import (
    ImportDisabledError,
    ImportJobError,
    ImportJobStateError,
    ImportSourceError,
)
from apps.catalog.services.imports import (
    check_source,
    create_import_job,
    request_cancel,
    request_retry,
)
from apps.catalog.services.queries import consolidated_aptitude_values
from apps.catalog.services.sources.registry import is_supported
from apps.catalog.services.sync import (
    CatalogSyncError,
    approve_change,
    reject_change,
    sync_from_file,
)
from apps.core.permissions import admin_required

DEFAULT_CUTOFF = date(2026, 12, 1)


def _image_stats() -> dict[str, int]:
    return {
        "valid": ImageAsset.objects.filter(is_current=True, status=ImageAsset.Status.VALID).count(),
        "invalid": ImageAsset.objects.filter(
            is_current=True, status=ImageAsset.Status.INVALID
        ).count(),
        "missing": ImageAsset.objects.filter(
            is_current=True, status=ImageAsset.Status.MISSING
        ).count(),
    }


def _characters_without_image():
    return Character.objects.exclude(
        images__is_current=True,
        images__status=ImageAsset.Status.VALID,
    ).distinct()


def _last_failure(source: CatalogSource) -> ImportJob | None:
    return (
        ImportJob.objects.filter(source=source, status=ImportJob.Status.FAILED)
        .order_by("-finished_at", "-created_at")
        .first()
    )


def _external_sources() -> list[dict]:
    """Todas as fontes, com situação de elegibilidade e última execução."""
    rows = []
    for source in CatalogSource.objects.all():
        last_job = source.import_jobs.order_by("-created_at").first()
        failure = _last_failure(source)
        if not source.enabled:
            reason = "Fonte desabilitada."
        elif not source.adapter:
            reason = "Sem conector registrado."
        elif not is_supported(source):
            reason = f"Conector '{source.adapter}' não registrado."
        else:
            reason = ""
        rows.append(
            {
                "source": source,
                "eligible": not reason,
                "reason": reason,
                "last_job": last_job,
                "last_failure": failure,
            }
        )
    return rows


@admin_required
def catalog_status(request):
    last_sync = SyncRun.objects.select_related("source").first()
    pending_changes = SyncChange.objects.filter(status=SyncChange.Status.PENDING)
    context = {
        "last_sync": last_sync,
        "recent_runs": SyncRun.objects.select_related("source")[:5],
        "pending_changes": pending_changes.select_related("character", "version")[:10],
        "pending_count": pending_changes.count(),
        "character_count": Character.objects.count(),
        "image_stats": _image_stats(),
        "characters_without_image": _characters_without_image().count(),
        "sources": CatalogSource.objects.all(),
        "external_sources": _external_sources(),
        "import_enabled": settings.EXTERNAL_IMPORT_ENABLED,
        "recent_import_jobs": ImportJob.objects.select_related("source")[:5],
        "sync_form": CatalogSyncForm(),
    }
    return render(request, "admin/catalog/status.html", context)


@admin_required
@require_POST
def catalog_sync(request):
    form = CatalogSyncForm(request.POST, request.FILES)
    if not form.is_valid():
        messages.error(request, "Selecione uma fonte e um arquivo CSV válido.")
        return redirect("admin:catalog_status")

    source = form.cleaned_data["source"]
    uploaded = form.cleaned_data["file"]
    suffix = os.path.splitext(uploaded.name)[1] or ".csv"
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        for chunk in uploaded.chunks():
            handle.write(chunk)
        handle.close()
        run = sync_from_file(handle.name, source, triggered_by=request.user)
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass

    if run.status == SyncRun.Status.FAILED:
        messages.error(
            request,
            "A sincronização falhou; o catálogo não foi alterado. " + (run.error_message or ""),
        )
    elif run.changes.filter(status=SyncChange.Status.PENDING).exists():
        messages.warning(
            request,
            "Sincronização concluída com mudanças pendentes de aprovação.",
        )
    else:
        messages.success(request, "Catálogo sincronizado com sucesso.")

    return redirect("admin:catalog_sync_detail", sync_id=run.pk)


@admin_required
def catalog_sync_detail(request, sync_id: int):
    run = get_object_or_404(
        SyncRun.objects.select_related("source", "triggered_by"),
        pk=sync_id,
    )
    changes = run.changes.select_related("character", "version", "reviewed_by")
    return render(
        request,
        "admin/catalog/sync_detail.html",
        {"run": run, "changes": changes},
    )


@admin_required
@require_POST
def catalog_approve(request, change_id: int):
    change = get_object_or_404(SyncChange, pk=change_id)
    try:
        approve_change(change, request.user)
    except CatalogSyncError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Mudança aprovada e aplicada ao catálogo.")
    return redirect("admin:catalog_sync_detail", sync_id=change.sync_run_id)


@admin_required
@require_POST
def catalog_reject(request, change_id: int):
    change = get_object_or_404(SyncChange, pk=change_id)
    note = request.POST.get("note", "").strip()
    try:
        reject_change(change, request.user, note)
    except CatalogSyncError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "Mudança rejeitada.")
    return redirect("admin:catalog_sync_detail", sync_id=change.sync_run_id)


@admin_required
def catalog_characters(request):
    query = request.GET.get("q", "").strip()
    cutoff_raw = request.GET.get("cutoff", "")
    try:
        cutoff = date.fromisoformat(cutoff_raw) if cutoff_raw else DEFAULT_CUTOFF
    except ValueError:
        cutoff = DEFAULT_CUTOFF

    characters = Character.objects.prefetch_related(
        "versions",
        "images",
        "versions__version_aptitudes__aptitude",
    )
    if query:
        characters = characters.filter(
            Q(display_name__icontains=query) | Q(stable_id__icontains=query)
        )

    paginator = Paginator(characters.order_by("display_name"), 50)
    page = paginator.get_page(request.GET.get("page"))

    rows = []
    for character in page.object_list:
        rows.append(
            {
                "character": character,
                "aptitudes": consolidated_aptitude_values(character, cutoff),
                "eligible_versions": character.versions.filter(release_date_global__lte=cutoff),
                "image": character.images.filter(is_current=True).first(),
            }
        )

    return render(
        request,
        "admin/catalog/characters.html",
        {
            "page": page,
            "rows": rows,
            "query": query,
            "cutoff": cutoff,
        },
    )


@admin_required
def catalog_images(request):
    status = request.GET.get("status", "")
    assets = ImageAsset.objects.select_related("character", "source")
    if status in ImageAsset.Status.values:
        assets = assets.filter(status=status)

    return render(
        request,
        "admin/catalog/images.html",
        {
            "assets": assets.order_by("character__display_name")[:500],
            "status": status,
            "status_choices": ImageAsset.Status.choices,
            "stats": _image_stats(),
            "characters_without_image": _characters_without_image()
            .annotate(version_count=Count("versions"))
            .order_by("display_name"),
            "report": None,
        },
    )


@admin_required
@require_POST
def catalog_images_validate(request):
    report = validate_all_images()
    return render(
        request,
        "admin/catalog/images.html",
        {
            "assets": ImageAsset.objects.select_related("character", "source").order_by(
                "character__display_name"
            )[:500],
            "status": "",
            "status_choices": ImageAsset.Status.choices,
            "stats": _image_stats(),
            "characters_without_image": _characters_without_image()
            .annotate(version_count=Count("versions"))
            .order_by("display_name"),
            "report": report,
        },
    )


# ---------------------------------------------------------------------------
# Importação externa
# ---------------------------------------------------------------------------
@admin_required
def catalog_import(request):
    """Formulário (GET) e criação assíncrona de uma execução (POST)."""
    if request.method == "POST":
        form = ImportJobForm(request.POST)
        if form.is_valid():
            try:
                job = create_import_job(
                    form.cleaned_data["source"],
                    form.cleaned_data["kind"],
                    options={"image_scope": form.cleaned_data["image_scope"]},
                    triggered_by=request.user,
                )
            except ImportDisabledError as exc:
                messages.error(request, str(exc))
            except ImportSourceError as exc:
                form.add_error("source", str(exc))
            except ImportJobError as exc:
                form.add_error(None, str(exc))
            else:
                if getattr(job, "already_active", False):
                    messages.info(
                        request,
                        "Já existe uma execução ativa para esta fonte; "
                        "acompanhe a execução existente.",
                    )
                else:
                    messages.success(request, "Importação enfileirada.")
                return redirect("admin:catalog_import_detail", job_id=job.pk)
    else:
        form = ImportJobForm()

    return render(
        request,
        "admin/catalog/import_form.html",
        {
            "form": form,
            "import_enabled": settings.EXTERNAL_IMPORT_ENABLED,
            "sources": _external_sources(),
        },
    )


@admin_required
def catalog_import_list(request):
    jobs = ImportJob.objects.select_related("source", "triggered_by")
    status = request.GET.get("status", "")
    source_id = request.GET.get("source", "")
    if status in ImportJob.Status.values:
        jobs = jobs.filter(status=status)
    if source_id.isdigit():
        jobs = jobs.filter(source_id=int(source_id))

    paginator = Paginator(jobs.order_by("-created_at"), 25)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "admin/catalog/import_list.html",
        {
            "page": page,
            "status": status,
            "source_id": source_id,
            "status_choices": ImportJob.Status.choices,
            "sources": CatalogSource.objects.all(),
        },
    )


@admin_required
def catalog_import_detail(request, job_id: int):
    job = get_object_or_404(
        ImportJob.objects.select_related("source", "triggered_by", "cancelled_by", "sync_run"),
        pk=job_id,
    )
    return render(
        request,
        "admin/catalog/import_detail.html",
        {
            "job": job,
            "last_failure": _last_failure(job.source),
            "catalog_report": (job.report or {}).get("catalog") or {},
            "images_report": (job.report or {}).get("images") or {},
        },
    )


@admin_required
def catalog_import_status(request, job_id: int):
    job = get_object_or_404(ImportJob, pk=job_id)
    response = JsonResponse(
        {
            "id": job.pk,
            "status": job.status,
            "status_label": job.get_status_display(),
            "phase": job.phase,
            "phase_label": job.get_phase_display(),
            "progress": {
                "done": job.progress_done,
                "total": job.progress_total,
                "percent": job.progress_percent,
            },
            "current_step": job.current_step,
            "cancel_requested": job.cancel_requested,
            "error": job.error_message,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None,
            "terminal": job.is_terminal,
            "detail_url": reverse("admin:catalog_import_detail", args=[job.pk]),
        }
    )
    response["Cache-Control"] = "no-store"
    return response


@admin_required
@require_POST
def catalog_import_cancel(request, job_id: int):
    job = get_object_or_404(ImportJob, pk=job_id)
    try:
        request_cancel(job, request.user)
    except ImportJobStateError:
        return HttpResponse("Execução já encerrada.", status=409)
    messages.success(request, "Cancelamento registrado.")
    return redirect("admin:catalog_import_detail", job_id=job.pk)


@admin_required
@require_POST
def catalog_import_retry(request, job_id: int):
    job = get_object_or_404(ImportJob.objects.select_related("source"), pk=job_id)
    try:
        new_job = request_retry(job, request.user)
    except ImportJobStateError:
        return HttpResponse("A execução ainda está ativa.", status=409)
    except (ImportDisabledError, ImportSourceError) as exc:
        messages.error(request, str(exc))
        return redirect("admin:catalog_import_detail", job_id=job.pk)

    if getattr(new_job, "already_active", False):
        messages.info(request, "Já existe uma execução ativa para esta fonte.")
    else:
        messages.success(request, "Nova execução enfileirada.")
    return redirect("admin:catalog_import_detail", job_id=new_job.pk)


@admin_required
@require_POST
def catalog_source_check(request, source_id: int):
    source = get_object_or_404(CatalogSource, pk=source_id)
    try:
        result = check_source(source)
    except ImportSourceError as exc:
        return HttpResponse(str(exc), status=409)
    except Exception as exc:  # pragma: no cover - falha inesperada do conector
        messages.error(request, f"Falha ao verificar a fonte: {exc}")
        return redirect("admin:catalog_status")

    if result.ok:
        messages.success(request, f"Fonte disponível. {result.message}".strip())
    else:
        messages.error(request, f"Fonte indisponível: {result.message}")
    return redirect("admin:catalog_status")
