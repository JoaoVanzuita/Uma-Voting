"""Template tags compartilhadas de interface."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils import timezone

register = template.Library()

LOCAL_TIME_ZONE = ZoneInfo(settings.TIME_ZONE)

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
}


def _placeholder_url() -> str:
    return static("img/character-placeholder.webp")


@register.simple_tag
def image_url(image_asset) -> str:
    """URL local do asset válido ou o placeholder seguro."""
    if image_asset is None:
        return _placeholder_url()

    if getattr(image_asset, "status", None) != "valid" or not image_asset.file_path:
        return _placeholder_url()

    return f"{settings.MEDIA_URL}{image_asset.file_path.lstrip('/')}"


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


def _localize(value: datetime) -> datetime:
    if timezone.is_naive(value):
        value = timezone.make_aware(value, LOCAL_TIME_ZONE)
    return value.astimezone(LOCAL_TIME_ZONE)


@register.filter
def datetime_br(value: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Formata data/hora em America/Sao_Paulo (formato strftime)."""
    if not value:
        return "—"
    return _localize(value).strftime(fmt)


@register.filter
def date_br(value: date | datetime | None, fmt: str = "%d/%m/%Y") -> str:
    if not value:
        return "—"
    if isinstance(value, datetime):
        value = _localize(value)
    return value.strftime(fmt)
