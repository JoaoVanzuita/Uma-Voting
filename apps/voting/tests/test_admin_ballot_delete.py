"""Testes da exclusão administrativa de cédulas (FR-071–FR-075)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.voting.models import Ballot, BallotChoice, Mode
from apps.voting.services.ballots import (
    VotingNotOpenError,
    delete_ballot_admin,
    submit_ballot,
)
from apps.voting.services.lifecycle import close_voting
from apps.voting.tests.helpers import create_open_voting
from tests.factories import AdminUserFactory, OpenVotingFactory, ParticipantFactory

pytestmark = pytest.mark.django_db


def test_exclusao_administrativa_remove_cedula_e_permite_novo_voto():
    voting, participant, snapshots = create_open_voting(choices_count=2)
    ids = [snapshot.pk for snapshot in snapshots[:2]]
    ballot = submit_ballot(voting, participant, ids)

    deleted = delete_ballot_admin(voting, participant, AdminUserFactory())

    assert deleted is True
    assert not Ballot.objects.filter(pk=ballot.pk).exists()
    assert not BallotChoice.objects.filter(ballot_id=ballot.pk).exists()

    new_ballot = submit_ballot(voting, participant, ids)
    assert new_ballot.pk != ballot.pk


def test_exclusao_sem_cedula_e_noop():
    voting, participant, _snapshots = create_open_voting(choices_count=1)

    assert delete_ballot_admin(voting, participant, AdminUserFactory()) is False


def test_exclusao_bloqueada_apos_encerramento():
    voting, participant, snapshots = create_open_voting(choices_count=1)
    submit_ballot(voting, participant, [snapshots[0].pk])
    close_voting(voting, "admin")

    with pytest.raises(VotingNotOpenError):
        delete_ballot_admin(voting, participant, AdminUserFactory())


def test_exclusao_bloqueada_com_prazo_automatico_vencido():
    voting = OpenVotingFactory(
        close_mode=Mode.AUTOMATIC,
        closes_at=timezone.now() - timedelta(minutes=1),
    )
    participant = ParticipantFactory()

    with pytest.raises(VotingNotOpenError):
        delete_ballot_admin(voting, participant, AdminUserFactory())


def test_view_de_exclusao_nao_expoe_escolhas(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=2)
    submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:2]])
    mail.outbox.clear()

    response = client.post(
        reverse("admin:ballot_delete", args=[voting.pk, participant.pk]),
        follow=True,
    )

    body = response.content.decode()
    assert response.status_code == 200
    assert not Ballot.objects.filter(voting=voting, participant=participant).exists()
    assert "Cédula excluída" in body
    for snapshot in snapshots[:2]:
        assert snapshot.display_name not in body
    assert mail.outbox == []
