"""Testes de modelos, constraints e independência entre votações."""

from datetime import date, timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.voting.models import (
    Ballot,
    BallotChoice,
    Mode,
    VotingCharacterSnapshot,
    VotingEligibility,
    VotingStatus,
    VotingVersionSnapshot,
)
from tests.factories import (
    BallotFactory,
    CharacterFactory,
    OpenVotingFactory,
    ParticipantFactory,
    VotingCharacterSnapshotFactory,
    VotingEligibilityFactory,
    VotingFactory,
    VotingVersionSnapshotFactory,
)

pytestmark = pytest.mark.django_db


def test_valores_padrao_da_votacao():
    voting = VotingFactory()

    assert voting.choices_count == 3
    assert voting.catalog_cutoff_date == date(2026, 12, 1)
    assert voting.status == VotingStatus.DRAFT
    assert voting.open_mode == Mode.MANUAL
    assert voting.close_mode == Mode.MANUAL


def test_choices_count_deve_ser_positivo():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            VotingFactory(choices_count=0)


def test_modo_automatico_exige_opens_at():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            VotingFactory(open_mode=Mode.AUTOMATIC, opens_at=None)


def test_modo_automatico_exige_closes_at():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            VotingFactory(close_mode=Mode.AUTOMATIC, closes_at=None)


def test_closes_at_deve_ser_posterior_a_opens_at():
    now = timezone.now()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            VotingFactory(opens_at=now, closes_at=now - timedelta(minutes=1))


def test_status_invalido_e_rejeitado():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            VotingFactory(status="invalido")


def test_elegibilidade_unica_por_votacao_e_usuario():
    eligibility = VotingEligibilityFactory()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            VotingEligibility.objects.create(
                voting=eligibility.voting,
                user=eligibility.user,
            )


def test_snapshot_unico_por_votacao_e_personagem():
    snapshot = VotingCharacterSnapshotFactory()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            VotingCharacterSnapshot.objects.create(
                voting=snapshot.voting,
                source_character=snapshot.source_character,
                stable_id="outro-stable-id",
                display_name=snapshot.display_name,
            )


def test_snapshot_stable_id_unico_por_votacao():
    snapshot = VotingCharacterSnapshotFactory()
    other_character = CharacterFactory()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            VotingCharacterSnapshot.objects.create(
                voting=snapshot.voting,
                source_character=other_character,
                stable_id=snapshot.stable_id,
                display_name="Outra personagem",
            )


def test_version_snapshot_unico_por_snapshot_e_versao():
    version_snapshot = VotingVersionSnapshotFactory()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            VotingVersionSnapshot.objects.create(
                character_snapshot=version_snapshot.character_snapshot,
                source_version=version_snapshot.source_version,
                stable_id="outra-versao",
                release_date_global=date(2025, 3, 1),
            )


def test_uma_cedula_por_participante_e_votacao():
    ballot = BallotFactory()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Ballot.objects.create(voting=ballot.voting, participant=ballot.participant)


def test_escolha_unica_por_cedula_e_personagem():
    ballot = BallotFactory()
    choice = ballot.choices.first()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            BallotChoice.objects.create(
                ballot=ballot,
                character_snapshot=choice.character_snapshot,
            )


def test_duas_votacoes_abertas_simultaneas_com_cedulas_independentes():
    participant = ParticipantFactory()

    first = OpenVotingFactory(title="Primeira")
    second = OpenVotingFactory(title="Segunda")
    VotingEligibilityFactory(voting=first, user=participant)
    VotingEligibilityFactory(voting=second, user=participant)

    first_ballot = BallotFactory(voting=first, participant=participant)
    second_ballot = BallotFactory(voting=second, participant=participant)

    assert first_ballot.pk != second_ballot.pk
    assert Ballot.objects.filter(participant=participant).count() == 2
    assert Ballot.objects.filter(participant=participant, voting=first).exists()
    assert Ballot.objects.filter(participant=participant, voting=second).exists()
