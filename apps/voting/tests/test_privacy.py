"""Testes de privacidade de resultados, participação e cédulas."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.voting.services.ballots import get_own_ballot, submit_ballot
from apps.voting.services.lifecycle import close_voting
from apps.voting.tests.helpers import create_open_voting
from tests.factories import (
    AdminUserFactory,
    ParticipantFactory,
    VotingEligibilityFactory,
)

pytestmark = pytest.mark.django_db


def test_admin_ve_agregados_sem_associacao_participante_personagem(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    submit_ballot(voting, participant, [snapshots[0].pk])

    response = client.get(reverse("admin:voting_results", args=[voting.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    assert snapshots[0].display_name in body
    assert participant.username not in body


def test_admin_ve_participacao_sem_personagens(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    submit_ballot(voting, participant, [snapshots[0].pk])

    response = client.get(reverse("admin:voting_participation", args=[voting.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    assert participant.username in body
    assert "Votou" in body
    for snapshot in snapshots:
        assert snapshot.display_name not in body


def test_participante_nao_ve_resultado_durante_votacao(client):
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    submit_ballot(voting, participant, [snapshots[0].pk])
    client.force_login(participant)

    response = client.get(reverse("participant:result", args=[voting.pk]))

    assert response.status_code == 404


def test_participante_ve_resultado_apos_encerramento(client):
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    submit_ballot(voting, participant, [snapshots[0].pk])
    close_voting(voting, "admin")
    client.force_login(participant)

    response = client.get(reverse("participant:result", args=[voting.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    assert snapshots[0].display_name in body
    assert "1º" in body


def test_get_own_ballot_filtra_por_usuario():
    voting, first, snapshots = create_open_voting(choices_count=1, candidates=2)
    second = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=second)
    first_ballot = submit_ballot(voting, first, [snapshots[0].pk])
    second_ballot = submit_ballot(voting, second, [snapshots[1].pk])

    assert get_own_ballot(voting, first) == first_ballot
    assert get_own_ballot(voting, second) == second_ballot


def test_rota_de_cedula_filtra_pelo_request_user(client):
    voting, first, snapshots = create_open_voting(choices_count=1, candidates=2)
    second = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=second)
    submit_ballot(voting, first, [snapshots[0].pk])
    submit_ballot(voting, second, [snapshots[1].pk])
    client.force_login(first)

    response = client.get(reverse("participant:ballot", args=[voting.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    assert snapshots[0].display_name in body
    assert snapshots[1].display_name not in body


def test_admin_elegivel_ve_propria_cedula_somente_na_rota_participante(client):
    admin = AdminUserFactory()
    voting, _participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    VotingEligibilityFactory(voting=voting, user=admin)
    submit_ballot(voting, admin, [snapshots[0].pk])
    client.force_login(admin)

    admin_results = client.get(reverse("admin:voting_results", args=[voting.pk]))
    own_ballot = client.get(reverse("participant:ballot", args=[voting.pk]))

    assert snapshots[0].display_name in admin_results.content.decode()
    assert "Minha cédula" not in admin_results.content.decode()
    assert snapshots[0].display_name in own_ballot.content.decode()
