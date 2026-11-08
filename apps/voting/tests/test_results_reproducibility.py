"""Testes de reprodutibilidade dos resultados após mutações do catálogo."""

from __future__ import annotations

from datetime import date

import pytest

from apps.catalog.models import Aptitude, ImageAsset
from apps.voting.models import VotingCharacterSnapshot
from apps.voting.services.ballots import submit_ballot
from apps.voting.services.results import aggregate_results
from tests.factories import (
    CharacterFactory,
    CharacterVersionAptitudeFactory,
    CharacterVersionFactory,
    ImageAssetFactory,
    OpenVotingFactory,
    ParticipantFactory,
    VotingCharacterSnapshotFactory,
    VotingEligibilityFactory,
    VotingVersionAptitudeSnapshotFactory,
    VotingVersionSnapshotFactory,
)

pytestmark = pytest.mark.django_db


def test_resultado_reproduz_snapshot_mesmo_apos_mudanca_de_catalogo_e_imagem():
    voting = OpenVotingFactory(choices_count=1)
    participant = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=participant)

    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    image = ImageAssetFactory(character=character, is_current=True)
    version = CharacterVersionFactory(
        character=character,
        stable_id="tokai-teio-v1",
        release_date_global=date(2025, 6, 26),
    )
    aptitude = Aptitude.objects.get(category="strategy", value="pace")
    CharacterVersionAptitudeFactory(version=version, aptitude=aptitude)

    snapshot = VotingCharacterSnapshotFactory(
        voting=voting,
        source_character=character,
        stable_id=character.stable_id,
        display_name=character.display_name,
        image_asset=image,
    )
    version_snapshot = VotingVersionSnapshotFactory(
        character_snapshot=snapshot,
        source_version=version,
        stable_id=version.stable_id,
        release_date_global=version.release_date_global,
    )
    VotingVersionAptitudeSnapshotFactory(
        version_snapshot=version_snapshot,
        aptitude=aptitude,
    )
    submit_ballot(voting, participant, [snapshot.pk])

    before = aggregate_results(voting)
    assert before[0].display_name == "Tokai Teio"
    assert before[0].image_asset.pk == image.pk
    assert before[0].votes == 1

    character.display_name = "Tokai Teio Renomeada"
    character.save(update_fields=["display_name"])
    version.display_name = "Versão renomeada"
    version.release_date_global = date(2025, 12, 24)
    version.save(update_fields=["display_name", "release_date_global"])

    ImageAsset.objects.filter(pk=image.pk).update(is_current=False)
    ImageAssetFactory(character=character, is_current=True)

    after = aggregate_results(voting)

    assert after[0].display_name == "Tokai Teio"
    assert after[0].image_asset.pk == image.pk
    assert after[0].votes == before[0].votes
    assert VotingCharacterSnapshot.objects.get(pk=snapshot.pk).display_name == "Tokai Teio"
