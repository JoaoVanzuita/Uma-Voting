"""Comando migrate_media_to_storage: dry-run, apply e idempotência."""

from __future__ import annotations

import hashlib
import io
import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from PIL import Image

from apps.catalog.management.commands.migrate_media_to_storage import (
    ITEM_DIVERGENT,
    ITEM_EXISTING,
    ITEM_MISSING,
    ITEM_SAVED,
    migrate_media,
)
from apps.catalog.models import ImageAsset
from tests.factories import ImageAssetFactory
from tests.media_storage import media_storage  # noqa: F401 - fixture global do módulo


def webp_bytes(color=(10, 20, 30)) -> bytes:
    image = Image.new("RGB", (8, 8), color)
    manifest = io.BytesIO()
    image.save(manifest, format="WEBP")
    return manifest.getvalue()


def local_asset(root, character="tokai-teio", data=None) -> str:
    data = data or webp_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    file_path = f"characters/{character}/{checksum}.webp"
    target = root / file_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return file_path


def test_dry_run_nao_grava(tmp_path):
    file_path = local_asset(tmp_path)
    target = _MemoryStorage()

    report = migrate_media(source_root=tmp_path, target_storage=target, file_paths=[file_path])

    assert report.count(ITEM_SAVED) == 1
    assert target.files == {}


def test_apply_envia_e_segunda_execucao_nao_duplica(tmp_path):
    file_path = local_asset(tmp_path)
    target = _MemoryStorage()

    first = migrate_media(
        source_root=tmp_path, target_storage=target, file_paths=[file_path], dry_run=False
    )
    second = migrate_media(
        source_root=tmp_path, target_storage=target, file_paths=[file_path], dry_run=False
    )

    assert first.count(ITEM_SAVED) == 1
    assert second.count(ITEM_EXISTING) == 1
    assert list(target.files) == [file_path]
    # A origem nunca é apagada.
    assert (tmp_path / file_path).exists()


def test_objeto_divergente_nao_e_sobrescrito_sem_force(tmp_path):
    file_path = local_asset(tmp_path)
    target = _MemoryStorage()
    target.files[file_path] = b"outro-conteudo"

    report = migrate_media(
        source_root=tmp_path, target_storage=target, file_paths=[file_path], dry_run=False
    )

    assert report.count(ITEM_DIVERGENT) == 1
    assert report.has_failures
    assert target.files[file_path] == b"outro-conteudo"

    forced = migrate_media(
        source_root=tmp_path,
        target_storage=target,
        file_paths=[file_path],
        dry_run=False,
        force=True,
    )
    assert forced.count(ITEM_SAVED) == 1
    assert target.files[file_path] == (tmp_path / file_path).read_bytes()


def test_arquivo_ausente_e_path_traversal_sao_reportados(tmp_path):
    report = migrate_media(
        source_root=tmp_path,
        target_storage=_MemoryStorage(),
        file_paths=["characters/x/nao-existe.webp", "../segredo.webp"],
        dry_run=True,
    )

    assert report.count(ITEM_MISSING) == 1
    assert report.count("failed") == 1


def test_checksum_do_nome_divergente_e_rejeitado(tmp_path):
    checksum = "0" * 64
    file_path = f"characters/tokai-teio/{checksum}.webp"
    target = tmp_path / file_path
    target.parent.mkdir(parents=True)
    target.write_bytes(webp_bytes())

    report = migrate_media(
        source_root=tmp_path, target_storage=_MemoryStorage(), file_paths=[file_path]
    )

    assert report.count(ITEM_DIVERGENT) == 1


@pytest.mark.django_db
@pytest.mark.usefixtures("media_storage")
def test_comando_usa_image_assets_e_falha_quando_nao_ha_banco(tmp_path):
    file_path = local_asset(tmp_path)
    output = StringIO()

    with pytest.raises(CommandError, match="--manifest"):
        call_command("migrate_media_to_storage", "--source-root", str(tmp_path), stdout=output)

    ImageAssetFactory(file_path=file_path)
    call_command(
        "migrate_media_to_storage",
        "--source-root",
        str(tmp_path),
        "--dry-run",
        "--json",
        stdout=output,
    )

    payload = json.loads(output.getvalue())
    assert payload["applied"] is False
    assert ImageAsset.objects.get().file_path == file_path


@pytest.mark.django_db
@pytest.mark.usefixtures("media_storage")
def test_comando_aceita_manifest_sem_banco(tmp_path):
    file_path = local_asset(tmp_path)
    manifest = tmp_path / "images.csv"
    manifest.write_text(f"character_stable_id,file\ntokai-teio,{file_path}\n", encoding="utf-8")
    output = StringIO()

    call_command(
        "migrate_media_to_storage",
        "--source-root",
        str(tmp_path),
        "--manifest",
        str(manifest),
        "--apply",
        "--storage-backend",
        _MEMORY_BACKEND,
        stdout=output,
    )

    assert "enviados=1" in output.getvalue()


class _MemoryStorage:
    """Storage em memória para validar o fluxo sem objeto remoto real."""

    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}

    def exists(self, name: str) -> bool:
        return name in self.files

    def open(self, name: str, mode: str = "rb"):
        if name not in self.files:
            raise FileNotFoundError(name)
        return _BytesFile(self.files[name])

    def save(self, name: str, content, max_length=None) -> str:
        self.files[name] = content.read()
        return name


class _BytesFile(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _memory_storage_factory():
    return _MemoryStorage()


_MEMORY_BACKEND = "apps.catalog.tests.test_migrate_media_to_storage._memory_storage_factory"
