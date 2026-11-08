"""Testes de integração das views de resultados e participação."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.voting.models import VotingStatus
from apps.voting.services.ballots import submit_ballot
from apps.voting.services.lifecycle import close_voting
from apps.voting.tests.helpers import create_open_voting
from tests.factories import (
    AdminUserFactory,
    ParticipantFactory,
    VotingEligibilityFactory,
)

pytestmark = pytest.mark.django_db


def test_resultados_administrativos_parciais(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    submit_ballot(voting, participant, [snapshots[0].pk])

    response = client.get(reverse("admin:voting_results", args=[voting.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Resultados parciais" in body
    assert snapshots[0].display_name in body


def test_resultados_administrativos_finais_com_posicoes(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    submit_ballot(voting, participant, [snapshots[0].pk])
    close_voting(voting, "admin")

    response = client.get(reverse("admin:voting_results", args=[voting.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Ranking final" in body
    assert "1º" in body


def test_participacao_administrativa(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=1)
    non_voter = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=non_voter)
    submit_ballot(voting, participant, [snapshots[0].pk])

    response = client.get(reverse("admin:voting_participation", args=[voting.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Votou" in body
    assert "Não votou" in body


def test_administrador_nao_acessa_cedula_de_outro_pela_rota_administrativa(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=1)
    submit_ballot(voting, participant, [snapshots[0].pk])

    # A única rota administrativa de cédula é a exclusão; não existe leitura de escolhas.
    response = client.get(
        reverse("admin:ballot_delete", args=[voting.pk, participant.pk])
    )

    assert response.status_code == 405


def test_participante_ve_link_para_resultado_apos_encerramento(client):
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=1)
    submit_ballot(voting, participant, [snapshots[0].pk])
    close_voting(voting, "admin")
    client.force_login(participant)

    response = client.get(reverse("participant:ballot", args=[voting.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Ver resultado" in body
    assert reverse("participant:result", args=[voting.pk]) in body


def test_resultado_de_votacao_cancelada_nao_e_oficial(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=1)
    submit_ballot(voting, participant, [snapshots[0].pk])
    voting.status = VotingStatus.CANCELLED
    voting.save(update_fields=["status"])

    response = client.get(reverse("admin:voting_results", args=[voting.pk]))

    assert response.status_code == 200
    assert "não possuem resultado oficial" in response.content.decode()


def test_participante_nao_elegivel_nao_ve_resultado(client):
    voting, _participant, _snapshots = create_open_voting(choices_count=1, candidates=1)
    close_voting(voting, "admin")
    outsider = ParticipantFactory()
    client.force_login(outsider)

    response = client.get(reverse("participant:result", args=[voting.pk]))

    assert response.status_code == 403
