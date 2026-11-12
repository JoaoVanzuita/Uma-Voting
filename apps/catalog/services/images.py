"""Validação e importação local de imagens de personagens."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError

from apps.catalog.models import CatalogSource, Character, ImageAsset

TARGET_SIZE = (256, 256)
MIN_SIZE = (128, 128)
MAX_PIXELS = 4096 * 4096
MAX_IMAGE_BYTES = 10 * 1024 * 1024
ALLOWED_FORMATS = {"WEBP", "PNG", "JPEG"}
ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_MANIFEST_SIZE = 5 * 1024 * 1024
LOCAL_SOURCE = "curadoria-local"


@dataclass(frozen=True)
class ImageValidation:
    status: str
    reason: str = ""
    width: int = 0
    height: int = 0
    checksum: str = ""


@dataclass(frozen=True)
class ImageIssue:
    character: str | None
    file: str
    message: str


@dataclass
class ImageValidationReport:
    checked: int = 0
    valid: int = 0
    invalid: int = 0
    missing: int = 0
    orphans: list[str] = field(default_factory=list)
    broken_references: list[str] = field(default_factory=list)
    duplicate_checksums: list[str] = field(default_factory=list)
    characters_without_image: list[str] = field(default_factory=list)
    issues: list[ImageIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.invalid or self.broken_references or self.orphans)


@dataclass(frozen=True)
class ImageImportItem:
    line: int
    character_stable_id: str
    file: str
    action: str
    destination: str = ""
    checksum: str = ""
    message: str = ""


@dataclass
class ImageImportReport:
    total: int = 0
    items: list[ImageImportItem] = field(default_factory=list)
    errors: list[ImageIssue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    applied: bool = False

    @property
    def created(self) -> int:
        return sum(1 for item in self.items if item.action == "create")

    @property
    def replaced(self) -> int:
        return sum(1 for item in self.items if item.action == "replace")

    @property
    def reused(self) -> int:
        return sum(1 for item in self.items if item.action == "reuse")


@dataclass(frozen=True)
class ImageStoreResult:
    """Resultado de ``store_image_bytes`` para uma imagem."""

    action: str
    checksum: str
    destination: str
    message: str
    warnings: tuple[str, ...] = ()


def _media_path(relative_path: str) -> Path:
    return Path(settings.MEDIA_ROOT) / relative_path


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _inspect_image(path: Path) -> tuple[Image.Image, str, str]:
    """Abre e valida a integridade; retorna imagem, formato e checksum do arquivo."""
    if path.stat().st_size > MAX_IMAGE_BYTES:
        raise ValueError("Arquivo de imagem excede o limite de 10 MB.")

    with Image.open(path) as probe:
        probe.verify()

    image = Image.open(path)
    image.load()

    if image.width * image.height > MAX_PIXELS:
        image.close()
        raise ValueError("Imagem excede o limite de 4096×4096 pixels.")

    fmt = (image.format or "").upper()
    if fmt not in ALLOWED_FORMATS:
        image.close()
        raise ValueError(f"Formato não permitido: {fmt or 'desconhecido'}.")

    checksum = _sha256(path.read_bytes())
    return image, fmt, checksum


def validate_image_asset(asset: ImageAsset) -> ImageValidation:
    """Valida um asset no disco e atualiza seus campos de estado."""
    path = _media_path(asset.file_path)

    if not path.exists():
        asset.status = ImageAsset.Status.MISSING
        asset.validated_at = timezone.now()
        asset.save(update_fields=["status", "validated_at"])
        return ImageValidation(ImageAsset.Status.MISSING, "Arquivo não encontrado.")

    try:
        image, _fmt, checksum = _inspect_image(path)
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        asset.status = ImageAsset.Status.INVALID
        asset.validated_at = timezone.now()
        asset.save(update_fields=["status", "validated_at"])
        return ImageValidation(ImageAsset.Status.INVALID, str(exc))

    width, height = image.size
    image.close()

    if width < MIN_SIZE[0] or height < MIN_SIZE[1]:
        asset.status = ImageAsset.Status.INVALID
        asset.width = max(width, 1)
        asset.height = max(height, 1)
        asset.validated_at = timezone.now()
        asset.save(update_fields=["status", "width", "height", "validated_at"])
        return ImageValidation(
            ImageAsset.Status.INVALID,
            f"Dimensões menores que {MIN_SIZE[0]}×{MIN_SIZE[1]}.",
            width,
            height,
            checksum,
        )

    if asset.checksum_sha256 and asset.checksum_sha256 != checksum:
        asset.status = ImageAsset.Status.INVALID
        asset.width = max(width, 1)
        asset.height = max(height, 1)
        asset.validated_at = timezone.now()
        asset.save(update_fields=["status", "width", "height", "validated_at"])
        return ImageValidation(
            ImageAsset.Status.INVALID,
            "Checksum divergente do arquivo em disco.",
            width,
            height,
            checksum,
        )

    asset.status = ImageAsset.Status.VALID
    asset.width = max(width, 1)
    asset.height = max(height, 1)
    asset.checksum_sha256 = checksum
    asset.validated_at = timezone.now()
    asset.save(update_fields=["status", "width", "height", "checksum_sha256", "validated_at"])
    return ImageValidation(ImageAsset.Status.VALID, "", width, height, checksum)


def validate_all_images() -> ImageValidationReport:
    """Valida o acervo completo, detectando órfãos, quebras e duplicidades."""
    report = ImageValidationReport()
    assets = list(ImageAsset.objects.select_related("character").all())
    report.checked = len(assets)

    referenced: set[str] = set()
    checksums: dict[str, set[int]] = {}

    for asset in assets:
        referenced.add(asset.file_path)
        result = validate_image_asset(asset)
        if result.status == ImageAsset.Status.VALID:
            report.valid += 1
        elif result.status == ImageAsset.Status.MISSING:
            report.missing += 1
            report.broken_references.append(asset.file_path)
            report.issues.append(
                ImageIssue(asset.character.stable_id, asset.file_path, result.reason)
            )
        else:
            report.invalid += 1
            report.issues.append(
                ImageIssue(asset.character.stable_id, asset.file_path, result.reason)
            )

        if asset.checksum_sha256:
            checksums.setdefault(asset.checksum_sha256, set()).add(asset.character_id)

    for checksum, character_ids in checksums.items():
        if len(character_ids) > 1:
            report.duplicate_checksums.append(checksum)

    characters_root = _media_path("characters")
    if characters_root.exists():
        for path in sorted(characters_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(settings.MEDIA_ROOT).as_posix()
            if relative not in referenced:
                report.orphans.append(relative)

    valid_character_ids = {
        asset.character_id
        for asset in assets
        if asset.is_current and asset.status == ImageAsset.Status.VALID
    }
    report.characters_without_image = list(
        Character.objects.exclude(pk__in=valid_character_ids)
        .order_by("display_name")
        .values_list("stable_id", flat=True)
    )

    return report


def _normalize_image(image: Image.Image) -> bytes:
    has_alpha = image.mode in {"RGBA", "LA", "PA"} or (
        image.mode == "P" and "transparency" in image.info
    )
    image = image.convert("RGBA" if has_alpha else "RGB")
    background = (0, 0, 0, 0) if has_alpha else (255, 255, 255)
    normalized = ImageOps.pad(
        image,
        TARGET_SIZE,
        method=Image.Resampling.LANCZOS,
        color=background,
    )
    buffer = io.BytesIO()
    normalized.save(buffer, format="WEBP", quality=90, method=6)
    return buffer.getvalue()


def _safe_source_path(source_dir: Path, file_value: str) -> Path:
    candidate = Path(file_value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("Caminho de arquivo inválido.")
    resolved = (source_dir / candidate).resolve()
    if not resolved.is_relative_to(source_dir.resolve()):
        raise ValueError("Arquivo fora do diretório de origem.")
    if resolved.is_symlink():
        target = resolved.resolve()
        if not target.is_relative_to(source_dir.resolve()):
            raise ValueError("Symlink aponta para fora do diretório de origem.")
    return resolved


def _read_manifest(manifest) -> list[dict[str, str]]:
    if hasattr(manifest, "read"):
        data = manifest.read()
    else:
        data = Path(manifest).read_bytes()

    if isinstance(data, bytes):
        if len(data) > MAX_MANIFEST_SIZE:
            raise ValueError("Manifesto excede o limite de 5 MB.")
        text = data.decode("utf-8-sig")
    else:
        text = data

    reader = csv.DictReader(io.StringIO(text), strict=True)
    reader.fieldnames = [name.strip() for name in (reader.fieldnames or [])]
    if not reader.fieldnames or not {"character_stable_id", "file"}.issubset(reader.fieldnames):
        raise ValueError("Manifesto deve conter as colunas character_stable_id e file.")
    return [row for row in reader]


def _inspect_bytes(data: bytes, *, max_bytes: int) -> tuple[Image.Image, str]:
    """Abre e valida a integridade de uma imagem em memória."""
    if len(data) > max_bytes:
        raise ValueError(f"Arquivo de imagem excede o limite de {max_bytes // (1024 * 1024)} MB.")

    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()

        image = Image.open(io.BytesIO(data))
        image.load()
    except UnidentifiedImageError as exc:
        raise ValueError("Imagem inválida ou formato não reconhecido.") from exc

    if image.width * image.height > MAX_PIXELS:
        image.close()
        raise ValueError("Imagem excede o limite de 4096×4096 pixels.")

    fmt = (image.format or "").upper()
    if fmt not in ALLOWED_FORMATS:
        image.close()
        raise ValueError(f"Formato não permitido: {fmt or 'desconhecido'}.")

    return image, fmt


def store_image_bytes(
    character: Character,
    data: bytes,
    *,
    source: CatalogSource,
    source_url: str = "",
    license_note: str = "",
    is_current: bool = True,
    max_bytes: int | None = None,
    dry_run: bool = False,
) -> ImageStoreResult:
    """Valida, normaliza e grava uma imagem recebida em memória.

    Reutiliza o mesmo pipeline da importação por manifesto: Pillow, WebP
    256×256, checksum SHA-256, destino content-addressed e preservação do
    arquivo anterior. O chamador converte ``ValueError``/``OSError`` em item do
    relatório e continua.
    """
    if source.name != LOCAL_SOURCE and not license_note.strip():
        raise ValueError("Fonte externa exige license_note e revisão manual antes de --apply.")

    limit = MAX_IMAGE_BYTES if max_bytes is None else max_bytes
    image, _fmt = _inspect_bytes(data, max_bytes=limit)

    try:
        width, height = image.size
        if width < MIN_SIZE[0] or height < MIN_SIZE[1]:
            raise ValueError(f"Dimensões mínimas de {MIN_SIZE[0]}×{MIN_SIZE[1]} não atendidas.")
        normalized_bytes = _normalize_image(image)
    finally:
        image.close()

    checksum = _sha256(normalized_bytes)
    destination = f"characters/{character.stable_id}/{checksum}.webp"
    destination_path = _media_path(destination)

    warnings: list[str] = []
    duplicates = ImageAsset.objects.filter(checksum_sha256=checksum).exclude(character=character)
    if duplicates.exists():
        warnings.append(f"Checksum {checksum[:12]}… também usado por outra personagem.")

    existing_checksum = ImageAsset.objects.filter(
        character=character,
        checksum_sha256=checksum,
    ).first()
    current_asset = ImageAsset.objects.filter(character=character, is_current=True).first()

    if existing_checksum is not None:
        action = "reuse"
        message = "Asset já existente para a personagem; reutilizado."
    elif current_asset is not None and is_current:
        action = "replace"
        message = "Substitui a imagem corrente; arquivo antigo é preservado."
    else:
        action = "create"
        message = "Nova imagem."

    if not dry_run:
        if not destination_path.exists():
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile(
                dir=destination_path.parent,
                prefix=".tmp-",
                suffix=".webp",
                delete=False,
            )
            try:
                handle.write(normalized_bytes)
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                handle.close()
            os.replace(handle.name, destination_path)

        with transaction.atomic():
            if is_current:
                ImageAsset.objects.filter(character=character, is_current=True).exclude(
                    pk=getattr(existing_checksum, "pk", None)
                ).update(is_current=False)
            if existing_checksum is None:
                ImageAsset.objects.create(
                    character=character,
                    file_path=destination,
                    is_current=is_current,
                    status=ImageAsset.Status.VALID,
                    checksum_sha256=checksum,
                    width=TARGET_SIZE[0],
                    height=TARGET_SIZE[1],
                    source=source,
                    source_url=source_url,
                    license_note=license_note,
                    validated_at=timezone.now(),
                )
            elif is_current and not existing_checksum.is_current:
                existing_checksum.is_current = True
                existing_checksum.validated_at = timezone.now()
                existing_checksum.save(update_fields=["is_current", "validated_at"])
            if existing_checksum is not None:
                existing_checksum.status = ImageAsset.Status.VALID
                existing_checksum.validated_at = timezone.now()
                existing_checksum.save(update_fields=["status", "validated_at"])

    return ImageStoreResult(
        action=action,
        checksum=checksum,
        destination=destination,
        message=message,
        warnings=tuple(warnings),
    )


def import_images(manifest, source_dir, *, dry_run: bool = True) -> ImageImportReport:
    """Importa ou substitui imagens a partir de um manifesto CSV.

    Cada item válido é aplicado em transação própria. Arquivos existentes nunca
    são sobrescritos e imagens antigas nunca são apagadas.
    """
    report = ImageImportReport()

    try:
        rows = _read_manifest(manifest)
    except (OSError, UnicodeDecodeError, ValueError, csv.Error) as exc:
        report.errors.append(ImageIssue(None, "", str(exc)))
        return report

    report.total = len(rows)
    base_dir = Path(source_dir)

    if not base_dir.exists() or not base_dir.is_dir():
        report.errors.append(ImageIssue(None, str(base_dir), "Diretório de origem inexistente."))
        return report

    for index, raw in enumerate(rows, start=2):
        if not any((value or "").strip() for value in raw.values() if isinstance(value, str)):
            continue

        character_stable_id = (raw.get("character_stable_id") or "").strip()
        file_value = (raw.get("file") or "").strip()

        try:
            character = Character.objects.get(stable_id=character_stable_id)
        except Character.DoesNotExist:
            report.errors.append(
                ImageIssue(
                    character_stable_id or None,
                    file_value,
                    f"Personagem '{character_stable_id}' não encontrada.",
                )
            )
            continue

        source_name = (raw.get("source") or "").strip() or LOCAL_SOURCE
        source = CatalogSource.objects.filter(name=source_name).first()
        if source is None:
            report.errors.append(
                ImageIssue(
                    character_stable_id,
                    file_value,
                    f"Fonte '{source_name}' não cadastrada.",
                )
            )
            continue

        license_note = (raw.get("license_note") or "").strip()
        if source.name != LOCAL_SOURCE and not license_note:
            report.errors.append(
                ImageIssue(
                    character_stable_id,
                    file_value,
                    "Fonte externa exige license_note e revisão manual antes de --apply.",
                )
            )
            continue

        try:
            source_path = _safe_source_path(base_dir, file_value)
            if source_path.suffix.lower() not in ALLOWED_EXTENSIONS:
                raise ValueError("Extensão de imagem não permitida.")
            if not source_path.is_file():
                raise ValueError("Arquivo não encontrado.")
            data = source_path.read_bytes()
        except (OSError, ValueError) as exc:
            report.errors.append(ImageIssue(character_stable_id, file_value, str(exc)))
            continue

        is_current_raw = (raw.get("is_current") or "true").strip().lower()
        is_current = is_current_raw not in {"false", "0", "nao", "não"}

        try:
            result = store_image_bytes(
                character,
                data,
                source=source,
                source_url=(raw.get("source_url") or "").strip(),
                license_note=license_note,
                is_current=is_current,
                dry_run=dry_run,
            )
        except (OSError, ValueError) as exc:
            report.errors.append(ImageIssue(character_stable_id, file_value, str(exc)))
            continue

        report.warnings.extend(result.warnings)
        report.items.append(
            ImageImportItem(
                line=index,
                character_stable_id=character.stable_id,
                file=file_value,
                action=result.action,
                destination=result.destination,
                checksum=result.checksum,
                message=result.message,
            )
        )

    report.applied = not dry_run
    return report
