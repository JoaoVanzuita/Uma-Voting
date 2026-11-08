"""Testes dos snapshots imutáveis criados na abertura (US6)."""

from __future__ import annotations

from datetime import date

import pytest
from django.db import DatabaseError, transaction

from apps.catalog.models import Aptitude, ImageAsset
from apps.voting.models import (
    Mode,
    Voting,
    VotingCharacterSnapshot,
    VotingStatus,
    VotingVersionSnapshot,
)
from apps.voting.services.snapshots import create_snapshots
from tests.factories import (
    CharacterFactory,
    CharacterVersionAptitudeFactory,
    CharacterVersionFactory,
    ImageAssetFactory,
    VotingFactory,
)

pytestmark = pytest.mark.django_db

CUTOFF = date(2026, 12, 1)


def make_voting(cutoff: date = CUTOFF) -> Voting:
    return VotingFactory(
        status=VotingStatus.DRAFT,
        open_mode=Mode.MANUAL,
        close_mode=Mode.MANUAL,
        catalog_cutoff_date=cutoff,
    )


def add_aptitude(version, category: str, value: str) -> None:
    CharacterVersionAptitudeFactory(
        version=version,
        aptitude=Aptitude.objects.get(category=category, value=value),
    )


def test_snapshot_respeita_cutoff_e_ignora_nao_lancadas():
    voting = make_voting()
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    CharacterVersionFactory(
        character=character,
        stable_id="original",
        release_date_global=date(2025, 6, 26),
    )
    CharacterVersionFactory(
        character=character,
        stable_id="no-corte",
        release_date_global=CUTOFF,
    )
    CharacterVersionFactory(
        character=character,
        stable_id="futura",
        release_date_global=date(2027, 1, 1),
    )
    CharacterVersionFactory(
        character=character,
        stable_id="sem-data",
        release_date_global=None,
    )

    create_snapshots(voting)

    snapshot = VotingCharacterSnapshot.objects.get(voting=voting)
    versions = set(
        snapshot.version_snapshots.values_list("stable_id", flat=True)
    )
    assert versions == {"original", "no-corte"}


def test_snapshot_denormaliza_nome_e_identificador():
    voting = make_voting()
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    CharacterVersionFactory(
        character=character,
        stable_id="original",
        release_date_global=date(2025, 6, 26),
    )

    create_snapshots(voting)
    character.display_name = "Nome Alterado"
    character.save(update_fields=["display_name"])

    snapshot = VotingCharacterSnapshot.objects.get(voting=voting)
    assert snapshot.display_name == "Tokai Teio"
    assert snapshot.stable_id == "tokai-teio"


def test_snapshot_preserva_aptidoes_por_versao():
    voting = make_voting()
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    first = CharacterVersionFactory(
        character=character,
        stable_id="original",
        release_date_global=date(2025, 6, 26),
    )
    second = CharacterVersionFactory(
        character=character,
        stable_id="peak-joy",
        release_date_global=date(2025, 7, 24),
    )
    add_aptitude(first, "strategy", "pace")
    add_aptitude(first, "distance", "medium")
    add_aptitude(second, "strategy", "late")
    add_aptitude(second, "surface", "dirt")

    create_snapshots(voting)

    snapshot = VotingCharacterSnapshot.objects.get(voting=voting)
    by_version = {
        version.stable_id: {
            link.aptitude.value for link in version.aptitude_snapshots.select_related("aptitude")
        }
        for version in snapshot.version_snapshots.all()
    }
    assert by_version == {"original": {"pace", "medium"}, "peak-joy": {"late", "dirt"}}


def test_snapshot_preserva_imagem_corrente_exata():
    voting = make_voting()
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    CharacterVersionFactory(
        character=character,
        stable_id="original",
        release_date_global=date(2025, 6, 26),
    )
    image = ImageAssetFactory(character=character, is_current=True)

    create_snapshots(voting)
    replacement = ImageAssetFactory(character=character, is_current=False)
    ImageAsset.objects.filter(pk=image.pk).update(is_current=False)
    ImageAsset.objects.filter(pk=replacement.pk).update(is_current=True)

    snapshot = VotingCharacterSnapshot.objects.get(voting=voting)
    assert snapshot.image_asset_id == image.pk


def test_personagem_sem_imagem_valida_usa_nulo():
    voting = make_voting()
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    CharacterVersionFactory(
        character=character,
        stable_id="original",
        release_date_global=date(2025, 6, 26),
    )
    ImageAssetFactory(character=character, is_current=True, status=ImageAsset.Status.INVALID)

    create_snapshots(voting)

    snapshot = VotingCharacterSnapshot.objects.get(voting=voting)
    assert snapshot.image_asset is None


def test_snapshots_sao_imutaveis():
    voting = make_voting()
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    CharacterVersionFactory(
        character=character,
        stable_id="original",
        release_date_global=date(2025, 6, 26),
    )
    create_snapshots(voting)
    snapshot = VotingCharacterSnapshot.objects.get(voting=voting)
    version = VotingVersionSnapshot.objects.get(character_snapshot=snapshot)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            VotingCharacterSnapshot.objects.filter(pk=snapshot.pk).update(
                display_name="Alterado"
            )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            VotingVersionSnapshot.objects.filter(pk=version.pk).update(
                stable_id="alterado"
            )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            snapshot.delete()
