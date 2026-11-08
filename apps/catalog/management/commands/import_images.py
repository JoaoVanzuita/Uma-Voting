"""Importa ou substitui imagens locais a partir de um manifesto CSV."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from apps.catalog.services.images import import_images


class Command(BaseCommand):
    help = "Importa imagens de personagens a partir de um manifesto CSV."

    def add_arguments(self, parser):
        parser.add_argument("--manifest", required=True)
        parser.add_argument("--source-dir", required=True)
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--dry-run", action="store_true", default=True)
        mode.add_argument("--apply", action="store_true")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        report = import_images(
            options["manifest"],
            options["source_dir"],
            dry_run=not options["apply"],
        )

        if options["as_json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "manifest": options["manifest"],
                        "dry_run": not options["apply"],
                        "total_rows": report.total,
                        "created": report.created,
                        "replaced": report.replaced,
                        "reused": report.reused,
                        "warnings": report.warnings,
                        "errors": [
                            {
                                "character": issue.character,
                                "file": issue.file,
                                "message": issue.message,
                            }
                            for issue in report.errors
                        ],
                        "items": [
                            {
                                "line": item.line,
                                "character": item.character_stable_id,
                                "file": item.file,
                                "action": item.action,
                                "destination": item.destination,
                            }
                            for item in report.items
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            self.stdout.write(
                f"{report.total} linha(s); {report.created} nova(s); "
                f"{report.replaced} substituição(ões); {report.reused} reutilizada(s); "
                f"{len(report.errors)} erro(s)."
            )
            for warning in report.warnings:
                self.stderr.write(f"Aviso: {warning}")
            for issue in report.errors:
                self.stderr.write(f"{issue.character or '—'} [{issue.file}]: {issue.message}")

        if report.errors:
            raise SystemExit(1)
