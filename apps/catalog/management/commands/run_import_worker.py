"""Worker dedicado da importação externa de catálogo e imagens."""

from __future__ import annotations

import json
import os
import signal
import socket
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.catalog.models import ImportJob
from apps.catalog.services.imports import claim_next_job, mark_stale_jobs, run_import_job

ADVISORY_LOCK_KEY = 0x554D41  # "UMA"


class Command(BaseCommand):
    help = "Processa a fila de importações externas em intervalos regulares."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=5)
        parser.add_argument(
            "--once",
            action="store_true",
            help="Executa um único ciclo e encerra (diagnóstico).",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emite o resumo do ciclo em JSON.",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Não imprime ciclos ociosos (usado no loop contínuo).",
        )

    def handle(self, *args, **options):
        if options["interval"] <= 0:
            raise CommandError("O intervalo deve ser positivo.")

        worker_id = f"import-worker-{socket.gethostname()}-{os.getpid()}"
        stop = {"requested": False}

        def _request_stop(signum, frame):  # noqa: ARG001
            stop["requested"] = True

        signal.signal(signal.SIGTERM, _request_stop)
        signal.signal(signal.SIGINT, _request_stop)

        cycle = self._run_cycle(worker_id)
        self._emit(cycle, options)

        if options["once"]:
            self._release_advisory_lock()
            return

        while not stop["requested"]:
            if cycle["processed"] or cycle["stale_jobs"]:
                time.sleep(options["interval"])
            cycle = self._run_cycle(worker_id)
            self._emit(cycle, options)

        self._release_advisory_lock()

    # ------------------------------------------------------------------
    # Ciclo
    # ------------------------------------------------------------------
    def _run_cycle(self, worker_id: str) -> dict:
        summary = {"worker_id": worker_id, "stale_jobs": 0, "processed": [], "errors": []}

        if not self._acquire_advisory_lock():
            summary["errors"].append("Outro worker está ativo; ciclo ignorado.")
            return summary

        try:
            summary["stale_jobs"] = mark_stale_jobs()
            while True:
                job = claim_next_job(worker_id)
                if job is None:
                    break
                try:
                    result = run_import_job(job.pk, worker_id)
                except Exception as exc:  # pragma: no cover - proteção do loop
                    summary["errors"].append(f"Job {job.pk}: {exc}")
                    break
                summary["processed"].append(self._serialize(result))
                if result.status == ImportJob.Status.FAILED:
                    break
        finally:
            self._release_advisory_lock()

        return summary

    # ------------------------------------------------------------------
    # Advisory lock e saída
    # ------------------------------------------------------------------
    def _acquire_advisory_lock(self) -> bool:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [ADVISORY_LOCK_KEY])
            return bool(cursor.fetchone()[0])

    def _release_advisory_lock(self) -> None:
        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [ADVISORY_LOCK_KEY])
        except Exception:  # pragma: no cover - encerramento defensivo
            pass

    def _serialize(self, job: ImportJob) -> dict:
        report = job.report or {}
        return {
            "job_id": job.pk,
            "source": job.source.name,
            "kind": job.kind,
            "status": job.status,
            "catalog": report.get("catalog") or {},
            "images": report.get("images") or {},
        }

    def _emit(self, summary: dict, options: dict) -> None:
        if (
            options.get("quiet")
            and not summary["processed"]
            and not summary["stale_jobs"]
            and not summary["errors"]
        ):
            return
        if options["as_json"]:
            self.stdout.write(json.dumps(summary, ensure_ascii=False))
            return
        self.stdout.write(
            "Ciclo concluído: "
            f"{len(summary['processed'])} job(s) processado(s); "
            f"{summary['stale_jobs']} stale; "
            f"{len(summary['errors'])} erro(s)."
        )
        for error in summary["errors"]:
            self.stderr.write(error)
