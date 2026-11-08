"""Views administrativas do catálogo e das imagens."""

from __future__ import annotations

import os
import tempfile
from datetime import date

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.catalog.forms import CatalogSyncForm
from apps.catalog.models import (
    CatalogSource,
    Character,
    ImageAsset,
    SyncChange,
    SyncRun,
)
from apps.catalog.services.images import validate_all_images
from apps.catalog.services.queries import consolidated_aptitude_values
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
