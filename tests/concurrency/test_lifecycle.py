"""Testes de concorrência do ciclo de vida das votações."""

from __future__ import annotations

import threading
import time
from datetime import date

import pytest
from django.db import connections

from apps.core.exceptions import PreconditionError
from apps.voting.models import Ballot, Mode, VotingStatus
from apps.voting.services.ballots import (
    VotingNotOpenError,
    delete_ballot_admin,
    submit_ballot,
)
from apps.voting.services.eligibility import add_default_eligible
from apps.voting.services.lifecycle import (
    VotingStateError,
    cancel_voting,
    close_voting,
    open_voting,
)
from apps.voting.tests.helpers import _aptitude, create_open_voting
from tests.factories import (
    AdminUserFactory,
    CharacterFactory,
    CharacterVersionAptitudeFactory,
    CharacterVersionFactory,
    ParticipantFactory,
    VotingFactory,
)

pytestmark = pytest.mark.django_db(transaction=True)

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
                aptitude=_aptitude(category, value),
            )


def make_draft(choices_count: int = 2):
    voting = VotingFactory(
        status=VotingStatus.DRAFT,
        choices_count=choices_count,
        catalog_cutoff_date=CUTOFF,
        open_mode=Mode.MANUAL,
        close_mode=Mode.MANUAL,
    )
    ParticipantFactory()
    add_default_eligible(voting)
    make_catalog(choices_count)
    return voting


def test_abertura_e_cancelamento_concorrentes():
    voting = make_draft(choices_count=2)
    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def open_worker():
        connections.close_all()
        try:
            barrier.wait(timeout=5)
            open_voting(voting, "admin")
            with lock:
                results.append("opened")
        except (VotingStateError, PreconditionError):
            with lock:
                results.append("blocked")
        finally:
            connections.close_all()

    def cancel_worker():
        connections.close_all()
        try:
            barrier.wait(timeout=5)
            cancel_voting(voting)
            with lock:
                results.append("cancelled")
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=open_worker),
        threading.Thread(target=cancel_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    voting.refresh_from_db()
    assert voting.status == VotingStatus.CANCELLED
    assert Ballot.objects.filter(voting=voting).count() == 0
    assert "cancelled" in results


def test_envio_e_encerramento_concorrentes():
    voting, participant, snapshots = create_open_voting(choices_count=2)
    ids = [snapshot.pk for snapshot in snapshots[:2]]
    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def submit_worker():
        connections.close_all()
        try:
            barrier.wait(timeout=5)
            submit_ballot(voting, participant, ids)
            with lock:
                results.append("submitted")
        except VotingNotOpenError:
            with lock:
                results.append("blocked")
        finally:
            connections.close_all()

    def close_worker():
        connections.close_all()
        try:
            barrier.wait(timeout=5)
            close_voting(voting, "admin")
            with lock:
                results.append("closed")
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=submit_worker),
        threading.Thread(target=close_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    voting.refresh_from_db()
    assert voting.status == VotingStatus.CLOSED
    assert "closed" in results
    assert set(results) <= {"submitted", "blocked", "closed"}
    assert Ballot.objects.filter(voting=voting).count() in {0, 1}


def test_exclusao_e_encerramento_concorrentes():
    voting, participant, snapshots = create_open_voting(choices_count=2)
    submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:2]])
    admin = AdminUserFactory()
    barrier = threading.Barrier(2)
    results: list[str] = []
    lock = threading.Lock()

    def delete_worker():
        connections.close_all()
        try:
            barrier.wait(timeout=5)
            deleted = delete_ballot_admin(voting, participant, admin)
            with lock:
                results.append("deleted" if deleted else "missing")
        except VotingNotOpenError:
            with lock:
                results.append("blocked")
        finally:
            connections.close_all()

    def close_worker():
        connections.close_all()
        try:
            barrier.wait(timeout=5)
            close_voting(voting, "admin")
            with lock:
                results.append("closed")
        finally:
            connections.close_all()

    threads = [
        threading.Thread(target=delete_worker),
        threading.Thread(target=close_worker),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    voting.refresh_from_db()
    assert voting.status == VotingStatus.CLOSED
    assert "closed" in results
    time.sleep(0.05)
    ballot_exists = Ballot.objects.filter(voting=voting, participant=participant).exists()
    if "deleted" in results:
        assert not ballot_exists
    else:
        assert ballot_exists
