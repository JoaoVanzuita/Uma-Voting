"""Regressão: importação externa não altera snapshots, cédulas ou resultados."""

from __future__ import annotations

import io
from datetime import date

import pytest

from apps.catalog.models import Character
from apps.catalog.services.importers import parse_catalog_csv
from apps.catalog.services.sync import sync_from_report
from apps.voting.models import BallotChoice
from apps.voting.services.results import aggregate_results
from tests.factories import (
    BallotChoiceFactory,
    BallotFactory,
    CatalogSourceFactory,
    CharacterFactory,
    CharacterVersionFactory,
    OpenVotingFactory,
    ParticipantFactory,
    VotingCharacterSnapshotFactory,
    VotingEligibilityFactory,
    VotingVersionSnapshotFactory,
)

pytestmark = pytest.mark.django_db

HEADER = (
    "character_stable_id,character_name,version_stable_id,version_name,"
    "release_date_global,strategy,distances,surfaces\n"
)


def report_with_changes():
    body = (
        "tokai-teio,Tokai Teio Renomeada,tokai-teio-original,Tokai Teio Renomeada (Original),"
        "2025-07-01,pace,medium;long,turf\n"
        "special-week,Special Week,special-week-original,Special Week (Original),"
        "2025-06-26,front,mile;medium;long,turf\n"
    )
    return parse_catalog_csv(io.BytesIO((HEADER + body).encode("utf-8")))


def test_importacao_externa_preserva_snapshots_cedulas_e_resultados():
    source = CatalogSourceFactory()
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    version = CharacterVersionFactory(
        character=character,
        stable_id="tokai-teio-original",
        display_name="Tokai Teio (Original)",
        release_date_global=date(2025, 6, 26),
    )
    voting = OpenVotingFactory()
    participant = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=participant)

    character_snapshot = VotingCharacterSnapshotFactory(
        voting=voting,
        source_character=character,
        stable_id="tokai-teio",
        display_name="Tokai Teio",
    )
    version_snapshot = VotingVersionSnapshotFactory(
        character_snapshot=character_snapshot,
        source_version=version,
        stable_id="tokai-teio-original",
        release_date_global=date(2025, 6, 26),
    )

    other_snapshots = []
    for index, name in enumerate(("Special Week", "Silence Suzuka"), start=1):
        other_character = CharacterFactory(
            stable_id=f"personagem-{index}",
            display_name=name,
        )
        other_snapshots.append(
            VotingCharacterSnapshotFactory(
                voting=voting,
                source_character=other_character,
                stable_id=other_character.stable_id,
                display_name=name,
            )
        )

    ballot = BallotFactory(voting=voting, participant=participant, choices=0)
    choice = BallotChoiceFactory(ballot=ballot, character_snapshot=character_snapshot)
    for snapshot in other_snapshots:
        BallotChoiceFactory(ballot=ballot, character_snapshot=snapshot)

    before_snapshot = {
        "stable_id": character_snapshot.stable_id,
        "display_name": character_snapshot.display_name,
        "version_stable_id": version_snapshot.stable_id,
        "version_release": version_snapshot.release_date_global,
        "image_asset_id": character_snapshot.image_asset_id,
    }
    before_results = [
        (row.stable_id, row.display_name, row.votes) for row in aggregate_results(voting)
    ]

    run = sync_from_report(
        report_with_changes(),
        source,
        apply_all=True,
        origin="external",
    )

    assert run.status == "success"
    character.refresh_from_db()
    assert character.display_name == "Tokai Teio Renomeada"
    assert Character.objects.filter(stable_id="special-week").exists()

    character_snapshot.refresh_from_db()
    version_snapshot.refresh_from_db()
    choice.refresh_from_db()

    assert {
        "stable_id": character_snapshot.stable_id,
        "display_name": character_snapshot.display_name,
        "version_stable_id": version_snapshot.stable_id,
        "version_release": version_snapshot.release_date_global,
        "image_asset_id": character_snapshot.image_asset_id,
    } == before_snapshot
    assert choice.character_snapshot_id == character_snapshot.pk
    assert BallotChoice.objects.filter(ballot=ballot).count() == 3

    after_results = [
        (row.stable_id, row.display_name, row.votes) for row in aggregate_results(voting)
    ]
    assert after_results == before_results
