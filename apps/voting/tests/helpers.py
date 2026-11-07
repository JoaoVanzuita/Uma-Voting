"""Helpers compartilhados dos testes de votações."""

from __future__ import annotations

from datetime import date

from django.utils.text import slugify

from apps.catalog.models import Aptitude
from tests.factories import (
    CharacterFactory,
    CharacterVersionAptitudeFactory,
    CharacterVersionFactory,
    OpenVotingFactory,
    ParticipantFactory,
    VotingCharacterSnapshotFactory,
    VotingEligibilityFactory,
    VotingVersionAptitudeSnapshotFactory,
    VotingVersionSnapshotFactory,
)

APTITUDE_LABELS = {
    ("strategy", "front"): "Front",
    ("strategy", "pace"): "Pace",
    ("strategy", "late"): "Late",
    ("strategy", "end"): "End",
    ("distance", "sprint"): "Sprint",
    ("distance", "mile"): "Mile",
    ("distance", "medium"): "Medium",
    ("distance", "long"): "Long",
    ("surface", "turf"): "Turf",
    ("surface", "dirt"): "Dirt",
}


def _aptitude(category: str, value: str) -> Aptitude:
    """Recria a aptidão canônica se um teste transacional tiver limpado a tabela."""
    aptitude, _created = Aptitude.objects.get_or_create(
        category=category,
        value=value,
        defaults={"label": APTITUDE_LABELS[(category, value)]},
    )
    return aptitude


def create_candidate(
    voting,
    name: str,
    *,
    strategy: str = "pace",
    distances=("medium",),
    surfaces=("turf",),
    release_date: date = date(2025, 1, 1),
    image_asset=None,
):
    """Cria personagem, versão, aptidões, snapshot e aptidões do snapshot."""
    slug = slugify(name)
    character = CharacterFactory(display_name=name, stable_id=slug)
    version = CharacterVersionFactory(
        character=character,
        stable_id=f"{slug}-v1",
        release_date_global=release_date,
    )

    for category, values in (
        ("strategy", (strategy,)),
        ("distance", distances),
        ("surface", surfaces),
    ):
        for value in values:
            aptitude = _aptitude(category, value)
            CharacterVersionAptitudeFactory(version=version, aptitude=aptitude)

    snapshot = VotingCharacterSnapshotFactory(
        voting=voting,
        source_character=character,
        display_name=name,
        stable_id=character.stable_id,
        image_asset=image_asset,
    )
    version_snapshot = VotingVersionSnapshotFactory(
        character_snapshot=snapshot,
        source_version=version,
        stable_id=version.stable_id,
        release_date_global=version.release_date_global or release_date,
    )
    for link in version.version_aptitudes.select_related("aptitude"):
        VotingVersionAptitudeSnapshotFactory(
            version_snapshot=version_snapshot,
            aptitude=link.aptitude,
        )

    return snapshot


def create_open_voting(
    *,
    choices_count: int = 3,
    candidates: int = 5,
    participant=None,
    **voting_kwargs,
):
    """Votação aberta com participante elegível e personagens no snapshot."""
    voting = OpenVotingFactory(choices_count=choices_count, **voting_kwargs)
    if participant is None:
        participant = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=participant)

    snapshots = [create_candidate(voting, f"Personagem {index}") for index in range(candidates)]
    return voting, participant, snapshots


def add_second_version(
    voting,
    snapshot,
    *,
    stable_suffix: str,
    strategy: str,
    distances=("sprint",),
    surfaces=("dirt",),
):
    """Adiciona uma segunda versão a um snapshot já existente."""
    version = CharacterVersionFactory(
        character=snapshot.source_character,
        stable_id=f"{snapshot.stable_id}-{stable_suffix}",
        release_date_global=date(2025, 2, 1),
    )

    for category, values in (
        ("strategy", (strategy,)),
        ("distance", distances),
        ("surface", surfaces),
    ):
        for value in values:
            aptitude = _aptitude(category, value)
            CharacterVersionAptitudeFactory(version=version, aptitude=aptitude)

    version_snapshot = VotingVersionSnapshotFactory(
        character_snapshot=snapshot,
        source_version=version,
        stable_id=version.stable_id,
        release_date_global=version.release_date_global,
    )
    for link in version.version_aptitudes.select_related("aptitude"):
        VotingVersionAptitudeSnapshotFactory(
            version_snapshot=version_snapshot,
            aptitude=link.aptitude,
        )
    return version_snapshot
