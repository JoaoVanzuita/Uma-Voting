"""Comando de limpeza das votações de teste criadas em produção."""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.voting.models import (
    Ballot,
    Voting,
    VotingCharacterSnapshot,
    VotingEligibility,
    VotingStatus,
)
from tests.factories import BallotFactory, OpenVotingFactory, VotingFactory

pytestmark = pytest.mark.django_db


def run(*args) -> str:
    output = StringIO()
    call_command("purge_test_votings", *args, stdout=output)
    return output.getvalue()


def test_dry_run_nao_altera_nada():
    VotingFactory(title="TESTE agendada", status=VotingStatus.SCHEDULED)
    VotingFactory(title="Eleição real", status=VotingStatus.DRAFT)

    out = run("--prefix", "TESTE ")

    assert "encontradas=1" in out
    assert Voting.objects.filter(title__startswith="TESTE ").count() == 1


def test_apply_apaga_apenas_votacoes_sem_cedulas():
    empty = VotingFactory(title="TESTE rascunho")
    closed = VotingFactory(title="TESTE encerrada", status=VotingStatus.CLOSED)
    real = VotingFactory(title="Eleição real", status=VotingStatus.DRAFT)

    out = run("--prefix", "TESTE ", "--apply", "--json")

    payload = json.loads(out)
    assert [item["id"] for item in payload["deleted"]] == [empty.pk]
    assert [item["id"] for item in payload["cancelled"]] == [closed.pk]
    closed.refresh_from_db()
    assert closed.status == VotingStatus.CANCELLED
    assert Voting.objects.filter(pk=real.pk).exists()


def test_votacao_aberta_sem_cedula_e_cancelada():
    voting = OpenVotingFactory(title="TESTE aberta sem voto")

    run("--prefix", "TESTE ", "--apply", "--json")

    voting.refresh_from_db()
    assert voting.status == VotingStatus.CANCELLED


def test_votacao_agendada_e_cancelada():
    voting = VotingFactory(title="TESTE agendada", status=VotingStatus.SCHEDULED)

    run("--prefix", "TESTE ", "--apply", "--json")

    voting.refresh_from_db()
    assert voting.status == VotingStatus.CANCELLED


def test_limpeza_remove_elegiveis_e_snapshots():
    voting = VotingFactory(title="TESTE rascunho")
    open_voting = OpenVotingFactory(title="TESTE aberta")
    run("--prefix", "TESTE ", "--apply", "--json")

    assert not VotingEligibility.objects.filter(voting__in=[voting.pk, open_voting.pk]).exists()
    assert not VotingCharacterSnapshot.objects.filter(voting=open_voting.pk).exists()


def test_votacao_com_cedula_e_cancelada_nao_excluida():
    voting = OpenVotingFactory(title="TESTE aberta")
    ballot = BallotFactory(voting=voting)

    run("--prefix", "TESTE ", "--apply", "--json")

    voting.refresh_from_db()
    assert voting.status == VotingStatus.CANCELLED
    assert not Ballot.objects.filter(pk=ballot.pk).exists()
    assert Voting.objects.filter(pk=voting.pk).exists()


def test_prefixo_vazio_e_rejeitado():
    with pytest.raises(CommandError, match="prefixo"):
        call_command("purge_test_votings", "--prefix", " ", "--apply")


def test_dry_run_e_apply_juntos_e_rejeitado():
    with pytest.raises(CommandError, match="não os dois"):
        call_command("purge_test_votings", "--dry-run", "--apply")
