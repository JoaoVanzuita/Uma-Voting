"""Template tags compartilhadas de interface."""

from __future__ import annotations

from datetime import date, datetime

from django import template
from django.templatetags.static import static

from apps.catalog.services import media
from apps.core.formatting import format_date_br, format_datetime_br

register = template.Library()

STATUS_LABELS = {
    # Votações
    "draft": "Rascunho",
    "scheduled": "Agendada",
    "open": "Aberta",
    "closed": "Encerrada",
    "cancelled": "Cancelada",
    # Imagens
    "valid": "Válida",
    "invalid": "Inválida",
    "missing": "Ausente",
    # Sincronização
    "running": "Em execução",
    "success": "Sucesso",
    "partial": "Parcial",
    "failed": "Falhou",
    "auto_applied": "Aplicada automaticamente",
    "pending": "Pendente",
    "approved": "Aprovada",
    "rejected": "Rejeitada",
    "queued": "Na fila",
}

STATUS_TONES = {
    "draft": "neutral",
    "scheduled": "warning",
    "open": "success",
    "closed": "neutral",
    "cancelled": "danger",
    "valid": "success",
    "invalid": "danger",
    "missing": "warning",
    "running": "info",
    "success": "success",
    "partial": "warning",
    "failed": "danger",
    "auto_applied": "success",
    "pending": "warning",
    "approved": "success",
    "rejected": "danger",
    "queued": "neutral",
}


def _placeholder_url() -> str:
    return static("img/character-placeholder.webp")


@register.simple_tag
def image_url(image_asset) -> str:
    """URL do asset válido no storage configurado ou o placeholder seguro."""
    if image_asset is None:
        return _placeholder_url()

    if getattr(image_asset, "status", None) != "valid" or not image_asset.file_path:
        return _placeholder_url()

    # No Railway o storage é S3 e a URL é assinada; no Compose é /media/.
    return media.asset_url(image_asset.file_path) or _placeholder_url()


@register.simple_tag
def placeholder_url() -> str:
    return _placeholder_url()


@register.inclusion_tag("components/status_badge.html")
def status_badge(status: str, label: str | None = None) -> dict[str, str]:
    """Badge textual com cor de reforço (nunca apenas cor)."""
    return {
        "status": status,
        "label": label or STATUS_LABELS.get(status, status),
        "tone": STATUS_TONES.get(status, "neutral"),
    }


@register.filter
def datetime_br(value: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Formata data/hora em America/Sao_Paulo (formato strftime)."""
    return format_datetime_br(value, fmt)


@register.filter
def date_br(value: date | datetime | None, fmt: str = "%d/%m/%Y") -> str:
    return format_date_br(value, fmt)
