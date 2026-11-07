"""Testes do serviço transacional de cédulas."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.voting.models import Ballot, Mode, VotingStatus
from apps.voting.services.ballots import (
    AlreadyVotedError,
    InvalidBallotError,
    NotEligibleError,
    VotingNotOpenError,
    get_own_ballot,
    submit_ballot,
)
from apps.voting.tests.helpers import create_candidate, create_open_voting
from tests.factories import OpenVotingFactory, ParticipantFactory, VotingEligibilityFactory

pytestmark = pytest.mark.django_db


def test_envio_valido_cria_cedula_com_quantidade_exata():
    voting, participant, snapshots = create_open_voting(choices_count=3)

    ballot = submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:3]])

    assert ballot.voting == voting
    assert ballot.participant == participant
    assert ballot.choices.count() == 3


def test_quantidade_menor_que_o_limite_e_rejeitada():
    voting, participant, snapshots = create_open_voting(choices_count=3)

    with pytest.raises(InvalidBallotError):
        submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:2]])

    assert Ballot.objects.count() == 0


def test_quantidade_maior_que_o_limite_e_rejeitada():
    voting, participant, snapshots = create_open_voting(choices_count=3)

    with pytest.raises(InvalidBallotError):
        submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:4]])

    assert Ballot.objects.count() == 0


def test_personagem_duplicada_e_rejeitada():
    voting, participant, snapshots = create_open_voting(choices_count=3)

    with pytest.raises(InvalidBallotError):
        submit_ballot(
            voting,
            participant,
            [snapshots[0].pk, snapshots[0].pk, snapshots[1].pk],
        )


def test_personagem_fora_do_snapshot_e_rejeitada():
    voting, participant, _snapshots = create_open_voting(choices_count=3)
    other_voting = OpenVotingFactory()
    foreign = create_candidate(other_voting, "Personagem Externa")
    own = create_candidate(voting, "Personagem Própria")

    with pytest.raises(InvalidBallotError):
        submit_ballot(voting, participant, [own.pk, foreign.pk, own.pk + 1000])


def test_identificador_invalido_e_rejeitado():
    voting, participant, _snapshots = create_open_voting(choices_count=3)

    with pytest.raises(InvalidBallotError):
        submit_ballot(voting, participant, ["a", "b", "c"])


def test_votacao_encerrada_nao_recebe_cedula():
    voting, participant, snapshots = create_open_voting(choices_count=3)
    voting.status = VotingStatus.CLOSED
    voting.save(update_fields=["status"])

    with pytest.raises(VotingNotOpenError):
        submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:3]])


def test_votacao_com_prazo_automatico_vencido_nao_recebe_cedula():
    voting, participant, snapshots = create_open_voting(
        choices_count=3,
        close_mode=Mode.AUTOMATIC,
        closes_at=timezone.now() - timedelta(minutes=1),
    )

    with pytest.raises(VotingNotOpenError):
        submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:3]])


def test_participante_sem_elegibilidade_e_rejeitado():
    voting, _participant, snapshots = create_open_voting(choices_count=3)
    outsider = ParticipantFactory()

    with pytest.raises(NotEligibleError):
        submit_ballot(voting, outsider, [snapshot.pk for snapshot in snapshots[:3]])

    assert Ballot.objects.count() == 0


def test_segundo_envio_e_rejeitado():
    voting, participant, snapshots = create_open_voting(choices_count=3)
    ids = [snapshot.pk for snapshot in snapshots[:3]]
    submit_ballot(voting, participant, ids)

    with pytest.raises(AlreadyVotedError):
        submit_ballot(voting, participant, ids)

    assert Ballot.objects.count() == 1


def test_get_own_ballot_retorna_somente_a_cedula_do_proprio_usuario():
    voting, participant, snapshots = create_open_voting(choices_count=3, candidates=6)
    other = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=other)

    own_ballot = submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:3]])
    other_ballot = submit_ballot(voting, other, [snapshot.pk for snapshot in snapshots[3:6]])

    assert get_own_ballot(voting, participant) == own_ballot
    assert get_own_ballot(voting, other) == other_ballot

    outsider = ParticipantFactory()
    assert get_own_ballot(voting, outsider) is None
