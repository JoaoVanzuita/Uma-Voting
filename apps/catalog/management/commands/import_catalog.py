"""Importa o catálogo curado em CSV, com prévia e aplicação explícita."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import CatalogSource, SyncChange
from apps.catalog.services.sync import (
    preview_catalog_file,
    sync_from_file,
)


class Command(BaseCommand):
    help = "Importa catálogo de CSV. Novas personagens são aplicadas; alterações ficam pendentes."

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="Caminho do arquivo catalog.csv")
        parser.add_argument(
            "--source",
            default="curadoria-local",
            help="Nome da CatalogSource (padrão: curadoria-local)",
        )
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", default=True)
        mode.add_argument("--apply", action="store_true")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        try:
            source = CatalogSource.objects.get(name=options["source"])
        except CatalogSource.DoesNotExist as exc:
            raise CommandError(f"Fonte '{options['source']}' não cadastrada.") from exc

        path = options["file"]
        apply = options["apply"]

        if not apply:
            preview = preview_catalog_file(path)
            if options["as_json"]:
                self.stdout.write(
                    json.dumps(
                        {
                            "file": path,
                            "source": source.name,
                            "dry_run": True,
                            "total_rows": preview.total_rows,
                            "new_characters": len(preview.new_characters),
                            "pending_changes": len(preview.pending_changes),
                            "ignored": len(preview.ignored_characters),
                            "errors": [
                                {
                                    "line": issue.line,
                                    "field": issue.field,
                                    "message": issue.message,
                                }
                                for issue in preview.errors
                            ],
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                )
            else:
                self.stdout.write(
                    f"{preview.total_rows} linha(s); "
                    f"{len(preview.new_characters)} personagem(ns) nova(s); "
                    f"{len(preview.pending_changes)} mudança(s) pendente(s); "
                    f"{len(preview.ignored_characters)} ignorada(s)."
                )
                for issue in preview.errors:
                    self.stderr.write(
                        f"Linha {issue.line or '—'} [{issue.field}]: {issue.message}"
                    )
            if preview.has_errors:
                raise CommandError("Arquivo inválido; o catálogo não foi alterado.")
            return

        run = sync_from_file(path, source)
        pending = run.changes.filter(status=SyncChange.Status.PENDING).count()
        applied = run.changes.filter(status=SyncChange.Status.AUTO_APPLIED).count()

        if options["as_json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "file": path,
                        "source": source.name,
                        "dry_run": False,
                        "sync_run_id": run.pk,
                        "status": run.status,
                        "total_rows": None,
                        "new_characters": applied,
                        "pending_changes": pending,
                        "errors": (
                            [{"message": run.error_message}] if run.error_message else []
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            self.stdout.write(f"Sincronização #{run.pk}: {run.get_status_display()}.")
            self.stdout.write(run.summary)
            if run.error_message:
                self.stderr.write(run.error_message)

        if run.status == "failed":
            raise CommandError("A sincronização falhou; o catálogo não foi alterado.")
