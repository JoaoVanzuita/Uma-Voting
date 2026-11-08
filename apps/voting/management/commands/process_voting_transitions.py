"""Executa uma passagem do agendador de transições de votações."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.voting.services.scheduler import process_due_transitions


class Command(BaseCommand):
    help = "Processa aberturas, encerramentos e cancelamentos devidos."

    def add_arguments(self, parser):
        parser.add_argument("--now", help="Data/hora ISO para simular o relógio")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        now = timezone.now()
        if options["now"]:
            parsed = parse_datetime(options["now"])
            if parsed is None:
                raise CommandError("Data/hora inválida; use o formato ISO 8601.")
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed)
            now = parsed

        report = process_due_transitions(now)

        if options["as_json"]:
            self.stdout.write(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
        elif not report.lock_acquired:
            self.stdout.write("Scheduler já em execução; nada foi processado.")
        else:
            self.stdout.write(
                f"processados={report.processed} abertos={report.opened} "
                f"encerrados={report.closed} cancelados={report.cancelled} "
                f"erros={len(report.errors)}"
            )
            for error in report.errors:
                self.stderr.write(error)

        if report.errors:
            raise CommandError("Uma ou mais transições falharam.")
