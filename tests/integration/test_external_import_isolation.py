"""Isolamento de mídia: páginas normais nunca apontam para imagens externas."""

from __future__ import annotations

import re
from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import ImageAsset
from apps.voting.services.snapshots import create_snapshots
from tests.factories import (
    AdminUserFactory,
    CatalogSourceFactory,
    CharacterFactory,
    CharacterVersionFactory,
    ImageAssetFactory,
    ImportJobFactory,
    OpenVotingFactory,
    ParticipantFactory,
    VotingEligibilityFactory,
    fixture_seed,
)

pytestmark = pytest.mark.django_db

EXTERNAL_URL = re.compile(r"^https?://", re.IGNORECASE)
IMG_SRC = re.compile(r'<img[^>]+src="([^"]*)"', re.IGNORECASE)


def assert_local_images(html: str) -> None:
    sources = IMG_SRC.findall(html)
    external = [src for src in sources if EXTERNAL_URL.match(src)]
    assert external == [], f"Imagens externas encontradas: {external}"
    assert "gametora.com" not in html
    assert "kuroco" not in html


@pytest.fixture
def scenario():
    source = CatalogSourceFactory(name="umamusume-global", adapter="umamusume-global")
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    CharacterVersionFactory(
        character=character,
        stable_id="tokai-teio-original",
        release_date_global=date(2025, 1, 1),
    )
    asset = ImageAssetFactory(
        character=character,
        file_path="characters/tokai-teio/abc.webp",
        is_current=True,
        status=ImageAsset.Status.VALID,
    )
    voting = OpenVotingFactory()
    participant = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=participant)
    with fixture_seed():
        create_snapshots(voting)
    job = ImportJobFactory(
        source=source,
        status="success",
        phase="finished",
        finished_at=timezone.now(),
    )
    return {
        "voting": voting,
        "participant": participant,
        "job": job,
        "asset": asset,
    }


def test_paginas_de_participante_usam_somente_midia_local(client, scenario):
    client.force_login(scenario["participant"])

    urls = [
        reverse("participant:home"),
        reverse("participant:voting_detail", args=[scenario["voting"].pk]),
        reverse("participant:character_grid", args=[scenario["voting"].pk]),
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        assert_local_images(response.content.decode())


def test_paginas_administrativas_usam_somente_midia_local(client, scenario):
    client.force_login(AdminUserFactory())

    urls = [
        reverse("admin:catalog_characters"),
        reverse("admin:catalog_images"),
        reverse("admin:catalog_import_detail", args=[scenario["job"].pk]),
    ]
    for url in urls:
        response = client.get(url)
        assert response.status_code == 200, url
        assert_local_images(response.content.decode())
