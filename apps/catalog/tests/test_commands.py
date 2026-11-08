"""Testes dos comandos de catálogo e imagens."""

from __future__ import annotations

import io
import json

import pytest
from PIL import Image

from apps.catalog.models import CatalogSource, Character, ImageAsset, SyncChange
from apps.catalog.services.sync import sync_from_file
from tests.factories import (
    AdminUserFactory,
    CharacterFactory,
    ImageAssetFactory,
)

HEADER = (
    "character_stable_id,character_name,version_stable_id,version_name,"
    "release_date_global,strategy,distances,surfaces\n"
)


def write_catalog(tmp_path, body: str) -> str:
    path = tmp_path / "catalog.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return str(path)


def png_bytes(size=(256, 256), color=(10, 20, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.mark.django_db
def test_import_catalog_dry_run_nao_altera_catalogo(tmp_path):
    from django.core.management import call_command

    path = write_catalog(
        tmp_path,
        "tokai-teio,Tokai Teio,original,Original,2025-06-26,pace,medium,turf\n",
    )
    out = io.StringIO()

    call_command("import_catalog", file=path, dry_run=True, stdout=out)

    assert "1 personagem(ns) nova(s)" in out.getvalue()
    assert not Character.objects.exists()


@pytest.mark.django_db
def test_import_catalog_apply_cria_personagem(tmp_path):
    from django.core.management import call_command

    path = write_catalog(
        tmp_path,
        "tokai-teio,Tokai Teio,original,Original,2025-06-26,pace,medium,turf\n",
    )
    out = io.StringIO()

    call_command("import_catalog", file=path, apply=True, stdout=out)

    assert Character.objects.filter(stable_id="tokai-teio").exists()


@pytest.mark.django_db
def test_sync_catalog_equivale_a_importacao_apply(tmp_path):
    from django.core.management import call_command

    path = write_catalog(
        tmp_path,
        "tokai-teio,Tokai Teio,original,Original,2025-06-26,pace,medium,turf\n",
    )

    call_command("sync_catalog", file=path, source="curadoria-local", stdout=io.StringIO())

    assert Character.objects.filter(stable_id="tokai-teio").exists()


@pytest.mark.django_db
def test_approve_e_reject_catalog_change(tmp_path):
    from django.core.management import call_command

    source = CatalogSource.objects.get(name="curadoria-local")
    CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    path = write_catalog(
        tmp_path,
        "tokai-teio,Tokai Teio,nova,Nova,2025-06-26,pace,medium,turf\n",
    )
    run = sync_from_file(path, source)
    change = run.changes.get(change_type=SyncChange.ChangeType.NEW_VERSION)
    admin = AdminUserFactory()

    call_command(
        "approve_catalog_change",
        id=change.pk,
        reviewer=admin.username,
        stdout=io.StringIO(),
    )
    change.refresh_from_db()
    assert change.status == SyncChange.Status.APPROVED

    path = write_catalog(
        tmp_path,
        "tokai-teio,Tokai Teio,outra,Outra,2025-06-26,pace,medium,turf\n",
    )
    run = sync_from_file(path, source)
    change = run.changes.get(change_type=SyncChange.ChangeType.NEW_VERSION)
    call_command(
        "reject_catalog_change",
        id=change.pk,
        reviewer=admin.username,
        note="divergente",
        stdout=io.StringIO(),
    )
    change.refresh_from_db()
    assert change.status == SyncChange.Status.REJECTED


@pytest.mark.django_db
def test_validate_images_json(tmp_path, settings):
    from django.core.management import call_command

    settings.MEDIA_ROOT = tmp_path
    character = CharacterFactory(stable_id="tokai-teio")
    file_path = "characters/tokai-teio/ok.webp"
    target = tmp_path / file_path
    target.parent.mkdir(parents=True)
    target.write_bytes(png_bytes())
    ImageAssetFactory(character=character, file_path=file_path, checksum_sha256="")
    out = io.StringIO()

    call_command("validate_images", as_json=True, stdout=out)

    payload = json.loads(out.getvalue())
    assert payload["valid"] == 1
    assert payload["characters_without_image"] == []


@pytest.mark.django_db
def test_import_images_apply_cria_asset(tmp_path, settings):
    from django.core.management import call_command

    settings.MEDIA_ROOT = tmp_path / "media"
    CharacterFactory(stable_id="tokai-teio")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "tokai.png").write_bytes(png_bytes())
    manifest = tmp_path / "images.csv"
    manifest.write_text(
        "character_stable_id,file,source,source_url,license_note\n"
        "tokai-teio,tokai.png,curadoria-local,,Local\n",
        encoding="utf-8",
    )

    call_command(
        "import_images",
        manifest=str(manifest),
        source_dir=str(source_dir),
        apply=True,
        stdout=io.StringIO(),
    )

    assert ImageAsset.objects.filter(character__stable_id="tokai-teio").count() == 1
