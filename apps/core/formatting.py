"""Formatação de datas e horas no fuso local da aplicação."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone

LOCAL_TIME_ZONE = ZoneInfo(settings.TIME_ZONE)


def localize(value: datetime) -> datetime:
    """Converte um datetime (ciente ou não) para ``America/Sao_Paulo``."""
    if timezone.is_naive(value):
        value = timezone.make_aware(value, LOCAL_TIME_ZONE)
    return value.astimezone(LOCAL_TIME_ZONE)


def format_datetime_br(value: datetime | None, fmt: str = "%d/%m/%Y %H:%M") -> str:
    """Formata data/hora no fuso local; ``—`` quando ausente."""
    if not value:
        return "—"
    return localize(value).strftime(fmt)


def format_date_br(value: date | datetime | None, fmt: str = "%d/%m/%Y") -> str:
    """Formata data no fuso local; ``—`` quando ausente."""
    if not value:
        return "—"
    if isinstance(value, datetime):
        value = localize(value)
    return value.strftime(fmt)
