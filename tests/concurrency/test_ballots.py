"""Testes de concorrência de envio de cédula."""

import threading
import time

import pytest
from django.db import connections, transaction

from apps.voting.models import Ballot, Voting, VotingStatus
from apps.voting.services.ballots import (
    AlreadyVotedError,
    VotingNotOpenError,
    submit_ballot,
)
from apps.voting.tests.helpers import create_open_voting

pytestmark = pytest.mark.django_db(transaction=True)


def test_dois_envios_concorrentes_apenas_um_vence():
    voting, participant, snapshots = create_open_voting(choices_count=3)
    ids = [snapshot.pk for snapshot in snapshots[:3]]

    barrier = threading.Barrier(2)
    results: list[tuple[str, object]] = []
    lock = threading.Lock()

    def worker():
        connections.close_all()
        try:
            barrier.wait(timeout=5)
            ballot = submit_ballot(voting, participant, ids)
            with lock:
                results.append(("ok", ballot.pk))
        except AlreadyVotedError:
            with lock:
                results.append(("already", None))
        except Exception as exc:  # pragma: no cover - diagnóstico de corrida
            with lock:
                results.append(("error", repr(exc)))
        finally:
            connections.close_all()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    outcomes = [outcome for outcome, _payload in results]
    assert sorted(outcomes) == ["already", "ok"]
    assert Ballot.objects.filter(voting=voting, participant=participant).count() == 1
    assert Ballot.objects.get(voting=voting, participant=participant).choices.count() == 3


def test_envio_apos_encerramento_concorrente_bloqueia_cedula():
    voting, participant, snapshots = create_open_voting(choices_count=3)
    ids = [snapshot.pk for snapshot in snapshots[:3]]

    close_started = threading.Event()
    release_close = threading.Event()
    close_finished = threading.Event()
    submit_result: dict[str, object] = {}

    def close_worker():
        connections.close_all()
        try:
            with transaction.atomic():
                locked = Voting.objects.select_for_update().get(pk=voting.pk)
                locked.status = VotingStatus.CLOSED
                locked.save(update_fields=["status"])
                close_started.set()
                release_close.wait(timeout=10)
            close_finished.set()
        finally:
            connections.close_all()

    def submit_worker():
        connections.close_all()
        try:
            submit_ballot(voting, participant, ids)
            submit_result["ok"] = True
        except VotingNotOpenError:
            submit_result["blocked"] = True
        finally:
            connections.close_all()

    close_thread = threading.Thread(target=close_worker)
    close_thread.start()
    assert close_started.wait(timeout=5)

    submit_thread = threading.Thread(target=submit_worker)
    submit_thread.start()
    time.sleep(0.2)

    release_close.set()
    close_thread.join(timeout=10)
    submit_thread.join(timeout=10)

    assert close_finished.is_set()
    assert submit_result.get("blocked") is True
    assert Ballot.objects.filter(voting=voting, participant=participant).count() == 0
