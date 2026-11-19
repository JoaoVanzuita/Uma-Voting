"""Testes de agregação e ranking de resultados (US7)."""

from __future__ import annotations

import pytest

from apps.voting.models import VotingEligibility, VotingStatus
from apps.voting.services.ballots import submit_ballot
from apps.voting.services.results import (
    ResultRow,
    aggregate_results,
    participation,
    participation_summary,
    rank_results,
)
from apps.voting.tests.helpers import create_open_voting
from tests.factories import ParticipantFactory, VotingEligibilityFactory

pytestmark = pytest.mark.django_db


def vote(voting, participant, snapshot):
    if not VotingEligibility.objects.filter(voting=voting, user=participant).exists():
        VotingEligibilityFactory(voting=voting, user=participant)
    return submit_ballot(voting, participant, [snapshot.pk])


def test_aggregate_results_conta_votos_por_personagem():
    voting, first_participant, snapshots = create_open_voting(
        choices_count=1,
        candidates=2,
    )
    vote(voting, first_participant, snapshots[0])
    vote(voting, ParticipantFactory(), snapshots[0])
    vote(voting, ParticipantFactory(), snapshots[1])

    rows = aggregate_results(voting)

    by_name = {row.display_name: row.votes for row in rows}
    assert by_name == {
        snapshots[0].display_name: 2,
        snapshots[1].display_name: 1,
    }


def test_aggregate_results_nao_expoe_participante():
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=1)
    vote(voting, participant, snapshots[0])

    row = aggregate_results(voting)[0]

    assert not hasattr(row, "participant_id")
    assert not hasattr(row, "participant")
    assert set(row.__dataclass_fields__) == {
        "stable_id",
        "display_name",
        "image_asset",
        "votes",
    }


def test_rank_results_aplica_dense_rank_e_exclui_zero():
    rows = [
        ResultRow("a", "Personagem A", None, 4),
        ResultRow("b", "Personagem B", None, 3),
        ResultRow("c", "Personagem C", None, 3),
        ResultRow("d", "Personagem D", None, 2),
        ResultRow("e", "Personagem E", None, 2),
        ResultRow("f", "Personagem F", None, 0),
    ]

    ranked = rank_results(rows)

    assert [(row.position, row.stable_id) for row in ranked] == [
        (1, "a"),
        (2, "b"),
        (2, "c"),
        (3, "d"),
        (3, "e"),
    ]
    assert all(row.stable_id != "f" for row in ranked)


def test_rank_results_nao_desempata_por_nome():
    rows = [
        ResultRow("z", "Zulu", None, 2),
        ResultRow("a", "Alfa", None, 2),
    ]

    ranked = rank_results(rows)

    assert [row.position for row in ranked] == [1, 1]
    assert [row.display_name for row in ranked] == ["Alfa", "Zulu"]


def test_participation_lista_quem_votou_e_quem_nao_votou():
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=1)
    non_voter = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=non_voter)
    vote(voting, participant, snapshots[0])

    rows = participation(voting)

    by_username = {row.username: row.voted for row in rows}
    assert by_username[participant.username] is True
    assert by_username[non_voter.username] is False


def test_participation_summary_agrega_cedulas_sem_expor_quem_votou():
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=1)
    non_voter = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=non_voter)
    vote(voting, participant, snapshots[0])

    summary = participation_summary(voting)

    assert summary.ballots == 1
    assert summary.eligible == 2
    assert summary.percent == 50
    assert set(summary.__dataclass_fields__) == {"ballots", "eligible", "percent"}


def test_resultado_cancelado_e_vazio():
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=1)
    vote(voting, participant, snapshots[0])
    voting.status = VotingStatus.CANCELLED
    voting.save(update_fields=["status"])

    assert aggregate_results(voting) == []


def test_resultado_nao_depende_do_catalogo_atual():
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    vote(voting, participant, snapshots[0])
    before = aggregate_results(voting)

    snapshots[0].source_character.display_name = "Nome alterado"
    snapshots[0].source_character.save(update_fields=["display_name"])

    after = aggregate_results(voting)
    assert [(row.stable_id, row.display_name, row.votes) for row in before] == [
        (row.stable_id, row.display_name, row.votes) for row in after
    ]
