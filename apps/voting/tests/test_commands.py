"""Testes dos comandos do ciclo de vida e do agendador."""

from __future__ import annotations

import io
import json
from datetime import date, timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.catalog.models import Aptitude
from apps.voting.models import Mode, VotingStatus
from apps.voting.services.eligibility import add_default_eligible
from tests.factories import (
    CharacterFactory,
    CharacterVersionAptitudeFactory,
    CharacterVersionFactory,
    ParticipantFactory,
    VotingFactory,
)

pytestmark = pytest.mark.django_db

CUTOFF = date(2026, 12, 1)


def make_due_voting() -> object:
    voting = VotingFactory(
        status=VotingStatus.DRAFT,
        choices_count=1,
        catalog_cutoff_date=CUTOFF,
        open_mode=Mode.AUTOMATIC,
        close_mode=Mode.AUTOMATIC,
        opens_at=timezone.now() - timedelta(minutes=5),
        closes_at=timezone.now() + timedelta(hours=1),
    )
    ParticipantFactory()
    add_default_eligible(voting)
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    version = CharacterVersionFactory(
        character=character,
        stable_id="tokai-teio-v1",
        release_date_global=CUTOFF,
    )
    CharacterVersionAptitudeFactory(
        version=version,
        aptitude=Aptitude.objects.get(category="strategy", value="pace"),
    )
    voting.status = VotingStatus.SCHEDULED
    voting.save(update_fields=["status"])
    return voting


def test_process_voting_transitions_json():
    voting = make_due_voting()
    out = io.StringIO()

    call_command("process_voting_transitions", as_json=True, stdout=out)

    payload = json.loads(out.getvalue())
    voting.refresh_from_db()
    assert payload["opened"] == 1
    assert voting.status == VotingStatus.OPEN


def test_run_scheduler_once():
    voting = make_due_voting()

    call_command("run_scheduler", interval=1, once=True, stdout=io.StringIO())

    voting.refresh_from_db()
    assert voting.status == VotingStatus.OPEN


def test_process_voting_transitions_rejeita_data_invalida():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command(
            "process_voting_transitions",
            now="data-invalida",
            stdout=io.StringIO(),
        )
