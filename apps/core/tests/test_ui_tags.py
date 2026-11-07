"""Testes das template tags compartilhadas de interface."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from apps.core.templatetags.ui_tags import (
    date_br,
    datetime_br,
    image_url,
    status_badge,
)


def test_image_url_usa_placeholder_sem_asset():
    assert image_url(None) == "/static/img/character-placeholder.webp"


def test_image_url_usa_media_para_asset_valido():
    asset = SimpleNamespace(status="valid", file_path="characters/tokai-teio/abc.webp")

    assert image_url(asset) == "/media/characters/tokai-teio/abc.webp"


def test_image_url_usa_placeholder_para_asset_invalido():
    asset = SimpleNamespace(status="invalid", file_path="characters/tokai-teio/abc.webp")

    assert image_url(asset) == "/static/img/character-placeholder.webp"


def test_datetime_br_converte_para_sao_paulo():
    value = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    assert datetime_br(value) == "01/01/2026 09:00"


def test_date_br_formata_data_iso():
    assert date_br(date(2026, 12, 1)) == "01/12/2026"


@pytest.mark.parametrize(
    ("status", "label", "tone"),
    [
        ("open", "Aberta", "success"),
        ("scheduled", "Agendada", "warning"),
        ("cancelled", "Cancelada", "danger"),
        ("valid", "Válida", "success"),
        ("missing", "Ausente", "warning"),
        ("failed", "Falhou", "danger"),
    ],
)
def test_status_badge_mapeia_rotulo_e_tom(status, label, tone):
    badge = status_badge(status)

    assert badge["label"] == label
    assert badge["tone"] == tone
