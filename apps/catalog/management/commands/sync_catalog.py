"""Executa a sincronização de uma fonte de arquivo configurada."""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Sincroniza o catálogo de uma fonte de arquivo (equivalente a import_catalog --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--source", default="curadoria-local")
        parser.add_argument("--file", required=True)
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        call_command(
            "import_catalog",
            file=options["file"],
            source=options["source"],
            apply=True,
            as_json=options["as_json"],
            stdout=self.stdout,
            stderr=self.stderr,
        )
