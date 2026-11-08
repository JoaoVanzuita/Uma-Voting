"""Valida o acervo local de imagens e reporta inconsistências."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.catalog.services.images import validate_all_images


class Command(BaseCommand):
    help = "Valida as imagens locais, atualizando status e detectando órfãos."

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Trata personagens sem imagem como falha (exit code 1).",
        )

    def handle(self, *args, **options):
        report = validate_all_images()

        if options["as_json"]:
            self.stdout.write(
                json.dumps(
                    {
                        "checked": report.checked,
                        "valid": report.valid,
                        "invalid": report.invalid,
                        "missing": report.missing,
                        "orphans": report.orphans,
                        "broken_references": report.broken_references,
                        "duplicate_checksums": report.duplicate_checksums,
                        "characters_without_image": report.characters_without_image,
                        "issues": [
                            {
                                "character": issue.character,
                                "file": issue.file,
                                "message": issue.message,
                            }
                            for issue in report.issues
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            self.stdout.write(
                f"{report.checked} asset(s) verificado(s); {report.valid} válido(s); "
                f"{report.invalid} inválido(s); {report.missing} ausente(s); "
                f"{len(report.orphans)} órfão(s); "
                f"{len(report.characters_without_image)} personagem(ns) sem imagem válida."
            )
            for issue in report.issues:
                self.stderr.write(
                    f"{issue.character or '—'} [{issue.file}]: {issue.message}"
                )
            for orphan in report.orphans:
                self.stderr.write(f"Órfão: {orphan}")
            for checksum in report.duplicate_checksums:
                self.stderr.write(f"Checksum duplicado entre personagens: {checksum}")

        if report.invalid or report.broken_references:
            raise CommandError("Há imagens inválidas ou referências quebradas.")
        if options["strict"] and report.characters_without_image:
            raise CommandError("Há personagens sem imagem válida.")
