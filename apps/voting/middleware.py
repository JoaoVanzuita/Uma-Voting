"""O agendador de transições acionado no início de requisições dinâmicas.

No Railway Free não há Cron Jobs nem orçamento para um serviço permanente de
scheduler. Quando ``DJANGO_SCHEDULER_MODE=on_request``, cada processo executa no
máximo uma passagem de ``process_due_transitions`` a cada intervalo, sempre
antes da view, para que ninguém veja uma votação agendada depois de ``opens_at``.

O advisory lock de ``process_due_transitions`` continua sendo a proteção global
entre processos; aqui só se evita chamadas repetidas e concorrentes por worker.
"""

from __future__ import annotations

import logging
import threading
import time

from django.conf import settings

logger = logging.getLogger("apps.voting.scheduler")

# Caminhos que nunca disparam o tick: saúde, estáticos e mídia.
IGNORED_PATH_PREFIXES = ("/health/", "/static/", "/media/")
TICKABLE_METHODS = frozenset({"GET", "HEAD"})


class RequestSchedulerMiddleware:
    """Roda uma passagem do scheduler, no máximo uma vez por intervalo."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.interval = settings.DJANGO_SCHEDULER_TICK_INTERVAL
        self._lock = threading.Lock()
        self._next_allowed = 0.0

    def __call__(self, request):
        self._tick(request)
        return self.get_response(request)

    def _should_tick(self, request) -> bool:
        if self.interval <= 0:
            return False
        if request.method not in TICKABLE_METHODS:
            return False
        return not request.path.startswith(IGNORED_PATH_PREFIXES)

    def _tick(self, request) -> None:
        if not self._should_tick(request):
            return
        if time.monotonic() < self._next_allowed:
            return
        if not self._lock.acquire(blocking=False):
            return
        try:
            # Double-check: outra thread pode ter tickado entre a checagem e o lock.
            if time.monotonic() < self._next_allowed:
                return
            # Import tardio: mantém o middleware leve e evita importar modelos
            # durante o carregamento de settings.
            from apps.voting.services.scheduler import process_due_transitions

            report = process_due_transitions()
            if report.processed or not report.lock_acquired:
                logger.info(
                    "Scheduler on_request processed=%s opened=%s closed=%s cancelled=%s",
                    report.processed,
                    report.opened,
                    report.closed,
                    report.cancelled,
                )
        except Exception:  # noqa: BLE001 - falha isolada não derruba a página
            logger.exception("Scheduler on_request falhou; requisição segue normalmente.")
        finally:
            self._next_allowed = time.monotonic() + self.interval
            self._lock.release()
