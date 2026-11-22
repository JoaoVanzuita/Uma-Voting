"""Migração idempotente do acervo local de mídia para o storage configurado."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.module_loading import import_string
from PIL import Image

from apps.catalog.models import ImageAsset
from apps.catalog.services import media

ITEM_SAVED = "saved"
ITEM_EXISTING = "existing"
ITEM_MISSING = "missing"
ITEM_DIVERGENT = "divergent"
ITEM_FAILED = "failed"


@dataclass
class MigrationItem:
    file_path: str
    action: str
    message: str = ""


@dataclass
class MigrationReport:
    items: list[MigrationItem] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def count(self, action: str) -> int:
        return sum(1 for item in self.items if item.action == action)

    @property
    def has_failures(self) -> bool:
        return bool(self.errors or self.count(ITEM_DIVERGENT) or self.count(ITEM_FAILED))

    def as_dict(self, *, applied: bool) -> dict:
        return {
            "applied": applied,
            "total": len(self.items),
            "saved": self.count(ITEM_SAVED),
            "existing": self.count(ITEM_EXISTING),
            "missing": self.count(ITEM_MISSING),
            "divergent": self.count(ITEM_DIVERGENT),
            "failed": self.count(ITEM_FAILED),
            "errors": self.errors,
            "items": [asdict(item) for item in self.items],
        }


def _local_target(root: Path, file_path: str) -> Path:
    """Resolve ``file_path`` dentro de ``root`` sem permitir path traversal."""
    candidate = Path(file_path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Caminho de arquivo inválido.")
    resolved = (root / candidate).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("Arquivo fora do diretório de origem.")
    return resolved


def _checksum_matches(file_path: str, data: bytes) -> bool:
    """Confere o SHA-256 embutido no nome content-addressed, quando houver."""
    expected = Path(file_path).stem.lower()
    if len(expected) == 64 and all(char in "0123456789abcdef" for char in expected):
        return hashlib.sha256(data).hexdigest() == expected
    return True


def _is_valid_image(file_path: str, data: bytes) -> bool:
    if Path(file_path).suffix.lower() not in {".webp", ".png", ".jpg", ".jpeg"}:
        return False
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
    except Exception:  # noqa: BLE001 - imagem corrompida vira divergente
        return False
    return True


def _relative_files(root: Path) -> list[str]:
    if not root.is_dir():
        return []
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file())


def _read(storage, name: str) -> bytes:
    with storage.open(name, "rb") as handle:
        return handle.read()


def migrate_media(
    *,
    source_root: Path | str,
    target_storage=None,
    file_paths: list[str] | None = None,
    dry_run: bool = True,
    force: bool = False,
) -> MigrationReport:
    """Copia o acervo local para o storage configurado, sem apagar a origem.

    Idempotente: objeto já existente com o mesmo conteúdo é ignorado. Um objeto
    divergente (mesmo caminho, conteúdo diferente) só é sobrescrito com
    ``--force``. ``ImageAsset.file_path`` nunca é alterado.
    """
    root = Path(source_root)
    storage = target_storage or media.get_storage()
    report = MigrationReport()

    if not root.is_dir():
        raise CommandError(f"Diretório de origem inexistente: {root}")

    paths = (
        _relative_files(root)
        if file_paths is None
        else sorted({path.lstrip("/") for path in file_paths})
    )

    for file_path in paths:
        try:
            source = _local_target(root, file_path)
        except ValueError as exc:
            report.items.append(MigrationItem(file_path, ITEM_FAILED, str(exc)))
            continue

        if not source.is_file():
            report.items.append(MigrationItem(file_path, ITEM_MISSING, "Arquivo local ausente."))
            continue

        data = source.read_bytes()

        if not _is_valid_image(file_path, data) or not _checksum_matches(file_path, data):
            report.items.append(
                MigrationItem(
                    file_path,
                    ITEM_DIVERGENT,
                    "Arquivo local inválido ou checksum divergente.",
                )
            )
            continue

        try:
            if storage.exists(file_path):
                if _read(storage, file_path) == data:
                    report.items.append(
                        MigrationItem(file_path, ITEM_EXISTING, "Objeto já existe e confere.")
                    )
                    continue
                if not force:
                    report.items.append(
                        MigrationItem(
                            file_path,
                            ITEM_DIVERGENT,
                            "Objeto remoto difere do local; use --force para sobrescrever.",
                        )
                    )
                    continue

            if not dry_run:
                storage.save(file_path, io.BytesIO(data), max_length=255)
                if _read(storage, file_path) != data:
                    report.items.append(
                        MigrationItem(
                            file_path, ITEM_FAILED, "Conteúdo remoto não confere após envio."
                        )
                    )
                    continue

            report.items.append(MigrationItem(file_path, ITEM_SAVED, "Enviado."))
        except Exception as exc:  # noqa: BLE001 - uma falha não interrompe o relatório
            report.errors.append(f"{file_path}: {exc}")
            report.items.append(MigrationItem(file_path, ITEM_FAILED, str(exc)))

    return report


class Command(BaseCommand):
    help = "Migra o acervo local de mídia para o storage configurado (idempotente)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--source-root",
            default=str(settings.MEDIA_ROOT),
            help="Diretório local com o acervo (padrão: MEDIA_ROOT).",
        )
        parser.add_argument("--dry-run", action="store_true", help="Apenas relata (padrão).")
        parser.add_argument("--apply", action="store_true", help="Envia os arquivos ausentes.")
        parser.add_argument(
            "--manifest",
            help="CSV character_stable_id,file: lista os arquivos sem depender do banco.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Sobrescreve objetos remotos divergentes.",
        )
        parser.add_argument("--json", action="store_true", dest="as_json")
        parser.add_argument(
            "--storage-backend",
            help="Backend de storage de destino (padrão: STORAGES['default']).",
        )

    def handle(self, *args, **options):
        if options["dry_run"] and options["apply"]:
            raise CommandError("Use --dry-run ou --apply, não os dois.")
        dry_run = not options["apply"]

        target_storage = None
        if options["storage_backend"]:
            target_storage = import_string(options["storage_backend"])()

        if options["manifest"]:
            file_paths = self._paths_from_manifest(options["manifest"])
        elif not ImageAsset.objects.exists():
            raise CommandError(
                "Nenhum ImageAsset encontrado; informe --manifest para migrar pelo CSV."
            )
        else:
            file_paths = list(ImageAsset.objects.values_list("file_path", flat=True))

        report = migrate_media(
            source_root=options["source_root"],
            target_storage=target_storage,
            file_paths=file_paths,
            dry_run=dry_run,
            force=options["force"],
        )

        if options["as_json"]:
            self.stdout.write(json.dumps(report.as_dict(applied=not dry_run), ensure_ascii=False))
        else:
            prefix = "dry-run" if dry_run else "apply"
            self.stdout.write(
                f"[{prefix}] enviados={report.count('saved')} "
                f"existentes={report.count('existing')} "
                f"ausentes={report.count('missing')} "
                f"divergentes={report.count('divergent')} "
                f"falhas={report.count('failed')}"
            )
            for item in report.items:
                if item.action not in {ITEM_SAVED, ITEM_EXISTING}:
                    self.stderr.write(f"{item.action}: {item.file_path} ({item.message})")
            for error in report.errors:
                self.stderr.write(error)

        if not dry_run and report.has_failures:
            raise CommandError("Migração concluída com divergências/falhas.")

    def _paths_from_manifest(self, manifest: str) -> list[str]:
        with Path(manifest).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if "file" not in (reader.fieldnames or []):
                raise CommandError("Manifesto deve conter a coluna file.")
            rows = list(reader)
        return [row["file"].strip() for row in rows if (row.get("file") or "").strip()]
