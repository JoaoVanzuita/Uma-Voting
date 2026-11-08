"""Loop do agendador de transições para o container dedicado."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.voting.services.scheduler import run_scheduler


class Command(BaseCommand):
    help = "Executa o agendador de transições a cada N segundos."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60)
        parser.add_argument(
            "--once",
            action="store_true",
            help="Executa apenas um ciclo (útil para diagnóstico).",
        )

    def handle(self, *args, **options):
        if options["interval"] <= 0:
            raise ValueError("O intervalo deve ser positivo.")

        self.stdout.write(
            f"Scheduler iniciado (intervalo={options['interval']}s)."
        )
        run_scheduler(
            interval=options["interval"],
            max_cycles=1 if options["once"] else None,
        )
