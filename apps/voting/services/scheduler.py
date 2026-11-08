"""Agendador de transições automáticas de votações."""

from __future__ import annotations

import logging
import signal
import threading
from dataclasses import dataclass, field
from datetime import datetime

from django.db import connection, transaction
from django.utils import timezone

from apps.core.exceptions import PreconditionError
from apps.voting.models import Mode, Voting, VotingStatus
from apps.voting.services.lifecycle import (
    VotingStateError,
    cancel_voting,
    close_voting,
    open_voting,
)

logger = logging.getLogger("apps.voting.scheduler")

ADVISORY_LOCK_KEY = 0x554D41  # "UMA"


@dataclass
class SchedulerReport:
    processed: int = 0
    opened: int = 0
    closed: int = 0
    cancelled: int = 0
    errors: list[str] = field(default_factory=list)
    lock_acquired: bool = True

    def as_dict(self) -> dict:
        return {
            "processed": self.processed,
            "opened": self.opened,
            "closed": self.closed,
            "cancelled": self.cancelled,
            "errors": self.errors,
            "lock_acquired": self.lock_acquired,
        }


def _acquire_lock() -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_KEY])
        return bool(cursor.fetchone()[0])


def _release_lock() -> None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_KEY])


def process_due_transitions(now: datetime | None = None) -> SchedulerReport:
    """Processa aberturas, encerramentos e cancelamentos devidos.

    Usa advisory lock para impedir execuções simultâneas e ``SKIP LOCKED``
    para não bloquear votações em processamento por outro worker.
    """
    now = now or timezone.now()
    report = SchedulerReport()

    if not _acquire_lock():
        report.lock_acquired = False
        logger.info("Scheduler ignorado: outra execução está ativa.")
        return report

    try:
        with transaction.atomic():
            due_open = list(
                Voting.objects.select_for_update(skip_locked=True).filter(
                    status=VotingStatus.SCHEDULED,
                    open_mode=Mode.AUTOMATIC,
                    opens_at__lte=now,
                )
            )
            due_close = list(
                Voting.objects.select_for_update(skip_locked=True).filter(
                    status=VotingStatus.OPEN,
                    close_mode=Mode.AUTOMATIC,
                    closes_at__lte=now,
                )
            )

        for voting in due_open:
            report.processed += 1
            try:
                if (
                    voting.close_mode == Mode.AUTOMATIC
                    and voting.closes_at is not None
                    and voting.closes_at <= now
                ):
                    cancel_voting(voting, reason="window_missed")
                    report.cancelled += 1
                else:
                    open_voting(voting, "scheduler")
                    report.opened += 1
            except PreconditionError as exc:
                cancel_voting(voting, reason=str(exc))
                report.cancelled += 1
            except VotingStateError:
                logger.info("Abertura ignorada voting_id=%s (estado alterado)", voting.pk)
            except Exception as exc:  # pragma: no cover - proteção por votação
                report.errors.append(f"voting {voting.pk}: {exc}")
                logger.exception("Falha ao abrir votação voting_id=%s", voting.pk)

        for voting in due_close:
            report.processed += 1
            try:
                close_voting(voting, "scheduler")
                report.closed += 1
            except VotingStateError:
                logger.info("Encerramento ignorado voting_id=%s (estado alterado)", voting.pk)
            except Exception as exc:  # pragma: no cover - proteção por votação
                report.errors.append(f"voting {voting.pk}: {exc}")
                logger.exception("Falha ao encerrar votação voting_id=%s", voting.pk)
    finally:
        _release_lock()

    logger.info(
        "Ciclo do scheduler processed=%s opened=%s closed=%s cancelled=%s errors=%s",
        report.processed,
        report.opened,
        report.closed,
        report.cancelled,
        len(report.errors),
    )
    return report


def run_scheduler(
    interval: int = 60,
    *,
    stop_event: threading.Event | None = None,
    max_cycles: int | None = None,
) -> None:
    """Executa ciclos periódicos até receber SIGTERM/SIGINT."""
    stop_event = stop_event or threading.Event()
    previous_handlers: dict[int, object] = {}

    def _handle_stop(_signum, _frame):
        stop_event.set()

    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            previous_handlers[signum] = signal.signal(signum, _handle_stop)
        except ValueError:  # fora da thread principal (testes)
            pass

    cycles = 0
    try:
        while not stop_event.is_set():
            try:
                process_due_transitions()
            except Exception:  # pragma: no cover - resiliência do loop
                logger.exception("Falha inesperada no ciclo do scheduler")

            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            stop_event.wait(interval)
    finally:
        for signum, handler in previous_handlers.items():
            try:
                signal.signal(signum, handler)
            except ValueError:  # pragma: no cover
                pass
