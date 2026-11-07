"""Comando de importação de participantes por CSV."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services.imports import import_participants


class Command(BaseCommand):
    help = "Importa participantes de um arquivo CSV de forma atômica."

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            required=True,
            help="Caminho do arquivo CSV.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Valida o arquivo sem gravar (padrão).",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Aplica a importação se não houver inconsistências.",
        )

    def handle(self, *args, **options):
        if options["dry_run"] and options["apply"]:
            raise CommandError("Use apenas --dry-run ou --apply.")

        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"Arquivo não encontrado: {path}")

        apply = bool(options["apply"])
        with path.open("rb") as file_obj:
            report = import_participants(file_obj, apply=apply)

        self.stdout.write(f"Linhas analisadas: {report.total_lines}")
        self.stdout.write(f"Válidas: {len(report.valid_rows)}")
        self.stdout.write(f"Importadas: {report.imported_count}")

        if report.errors:
            for issue in report.errors:
                line = issue.line if issue.line is not None else "—"
                value = issue.value or "—"
                self.stderr.write(f"Linha {line}: {value}: {issue.message}")
            raise CommandError("Importação cancelada; nenhum dado foi gravado.")

        if not apply:
            self.stdout.write(self.style.WARNING("Dry-run concluído. Use --apply para importar."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"{report.imported_count} participante(s) importado(s).")
            )
