"""Testes do agendador de transições (US6)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.catalog.models import Aptitude
from apps.voting.models import (
    Ballot,
    Mode,
    Voting,
    VotingStatus,
)
from apps.voting.services import scheduler
from apps.voting.services.eligibility import add_default_eligible
from apps.voting.services.scheduler import (
    SchedulerReport,
    process_due_transitions,
    run_scheduler,
)
from tests.factories import (
    CharacterFactory,
    CharacterVersionAptitudeFactory,
    CharacterVersionFactory,
    OpenVotingFactory,
    ParticipantFactory,
    VotingFactory,
)

pytestmark = pytest.mark.django_db

CUTOFF = date(2026, 12, 1)


def make_catalog(count: int) -> None:
    for index in range(count):
        character = CharacterFactory(
            stable_id=f"personagem-{index}",
            display_name=f"Personagem {index}",
        )
        version = CharacterVersionFactory(
            character=character,
            stable_id=f"personagem-{index}-v1",
            release_date_global=CUTOFF,
        )
        for category, value in (
            ("strategy", "pace"),
            ("distance", "medium"),
            ("surface", "turf"),
        ):
            CharacterVersionAptitudeFactory(
                version=version,
                aptitude=Aptitude.objects.get(category=category, value=value),
            )


def make_scheduled(
    *,
    opens_at,
    closes_at,
    choices_count: int = 2,
    eligible: bool = True,
    catalog: bool = True,
) -> Voting:
    voting = VotingFactory(
        status=VotingStatus.DRAFT,
        choices_count=choices_count,
        catalog_cutoff_date=CUTOFF,
        open_mode=Mode.AUTOMATIC,
        close_mode=Mode.AUTOMATIC,
        opens_at=opens_at,
        closes_at=closes_at,
    )
    if eligible:
        ParticipantFactory()
        add_default_eligible(voting)
    if catalog:
        make_catalog(choices_count)
    voting.status = VotingStatus.SCHEDULED
    voting.save(update_fields=["status"])
    return voting


def test_abertura_devida_e_processada():
    voting = make_scheduled(
        opens_at=timezone.now() - timedelta(minutes=5),
        closes_at=timezone.now() + timedelta(hours=1),
    )

    report = process_due_transitions()

    voting.refresh_from_db()
    assert report.opened == 1
    assert report.errors == []
    assert voting.status == VotingStatus.OPEN


def test_encerramento_devido_e_processado():
    voting = OpenVotingFactory(
        close_mode=Mode.AUTOMATIC,
        closes_at=timezone.now() - timedelta(minutes=1),
    )

    report = process_due_transitions()

    voting.refresh_from_db()
    assert report.closed == 1
    assert voting.status == VotingStatus.CLOSED


def test_janela_perdida_cancela_sem_cedulas():
    voting = make_scheduled(
        opens_at=timezone.now() - timedelta(hours=2),
        closes_at=timezone.now() - timedelta(hours=1),
    )

    report = process_due_transitions()

    voting.refresh_from_db()
    assert report.cancelled == 1
    assert voting.status == VotingStatus.CANCELLED
    assert Ballot.objects.filter(voting=voting).count() == 0


def test_agendada_sem_elegiveis_e_cancelada():
    voting = make_scheduled(
        opens_at=timezone.now() - timedelta(minutes=5),
        closes_at=timezone.now() + timedelta(hours=1),
        eligible=False,
    )

    report = process_due_transitions()

    voting.refresh_from_db()
    assert report.cancelled == 1
    assert voting.status == VotingStatus.CANCELLED


def test_nao_processa_antes_do_horario():
    opens_at = timezone.now() + timedelta(hours=1)
    voting = make_scheduled(
        opens_at=opens_at,
        closes_at=opens_at + timedelta(hours=1),
    )

    report = process_due_transitions(now=timezone.now())

    voting.refresh_from_db()
    assert report.processed == 0
    assert voting.status == VotingStatus.SCHEDULED


def test_processamento_e_idempotente():
    voting = make_scheduled(
        opens_at=timezone.now() - timedelta(minutes=5),
        closes_at=timezone.now() + timedelta(hours=1),
    )

    first = process_due_transitions()
    second = process_due_transitions()

    voting.refresh_from_db()
    assert first.opened == 1
    assert second.processed == 0
    assert voting.status == VotingStatus.OPEN


def test_lock_impede_execucao_simultanea(monkeypatch):
    monkeypatch.setattr(scheduler, "_acquire_lock", lambda: False)

    report = process_due_transitions()

    assert report.lock_acquired is False
    assert report.processed == 0


def test_run_scheduler_executa_um_ciclo(monkeypatch):
    calls: list[int] = []

    def fake_process(*_args, **_kwargs):
        calls.append(1)
        return SchedulerReport()

    monkeypatch.setattr(scheduler, "process_due_transitions", fake_process)

    run_scheduler(interval=0, max_cycles=1)

    assert calls == [1]


def test_falha_de_abertura_cancela_votacao(monkeypatch):
    voting = make_scheduled(
        opens_at=timezone.now() - timedelta(minutes=5),
        closes_at=timezone.now() + timedelta(hours=1),
    )

    def failing_open(*_args, **_kwargs):
        from apps.core.exceptions import PreconditionError

        raise PreconditionError("catálogo insuficiente")

    monkeypatch.setattr(scheduler, "open_voting", failing_open)

    report = process_due_transitions()

    voting.refresh_from_db()
    assert report.cancelled == 1
    assert voting.status == VotingStatus.CANCELLED
