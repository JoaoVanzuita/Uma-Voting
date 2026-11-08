"""Testes de validação e importação local de imagens."""

from __future__ import annotations

import io

import pytest
from PIL import Image

from apps.catalog.models import ImageAsset
from apps.catalog.services.images import (
    import_images,
    validate_all_images,
    validate_image_asset,
)
from tests.factories import CatalogSourceFactory, CharacterFactory, ImageAssetFactory


def image_bytes(size=(256, 256), color=(30, 90, 150), mode="RGB") -> bytes:
    image = Image.new(mode, size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def write_manifest(tmp_path, rows: str):
    path = tmp_path / "images.csv"
    path.write_text(
        "character_stable_id,file,source,source_url,license_note,is_current\n" + rows,
        encoding="utf-8",
    )
    return str(path)


@pytest.mark.django_db
def test_validacao_marca_imagem_valida_e_calcula_checksum(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    character = CharacterFactory(stable_id="tokai-teio")
    file_path = "characters/tokai-teio/original.webp"
    target = tmp_path / file_path
    target.parent.mkdir(parents=True)
    target.write_bytes(image_bytes())

    asset = ImageAssetFactory(
        character=character,
        file_path=file_path,
        checksum_sha256="",
        width=256,
        height=256,
        is_current=True,
    )

    result = validate_image_asset(asset)

    asset.refresh_from_db()
    assert result.status == ImageAsset.Status.VALID
    assert asset.status == ImageAsset.Status.VALID
    assert len(asset.checksum_sha256) == 64
    assert asset.validated_at is not None


@pytest.mark.django_db
def test_validacao_marca_arquivo_ausente(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    asset = ImageAssetFactory(file_path="characters/ausente.webp")

    result = validate_image_asset(asset)

    asset.refresh_from_db()
    assert result.status == ImageAsset.Status.MISSING
    assert asset.status == ImageAsset.Status.MISSING


@pytest.mark.django_db
def test_validacao_marca_checksum_divergente(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    file_path = "characters/checksum.webp"
    target = tmp_path / file_path
    target.parent.mkdir(parents=True)
    target.write_bytes(image_bytes())
    asset = ImageAssetFactory(
        file_path=file_path,
        checksum_sha256="0" * 64,
    )

    result = validate_image_asset(asset)

    asset.refresh_from_db()
    assert result.status == ImageAsset.Status.INVALID
    assert asset.status == ImageAsset.Status.INVALID


@pytest.mark.django_db
def test_importacao_dry_run_nao_grava(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    character = CharacterFactory(stable_id="tokai-teio")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "tokai.png").write_bytes(image_bytes())
    manifest = write_manifest(
        tmp_path,
        "tokai-teio,tokai.png,curadoria-local,,Acervo local autorizado,true\n",
    )

    report = import_images(manifest, source_dir, dry_run=True)

    assert not report.errors
    assert report.created == 1
    assert not ImageAsset.objects.filter(character=character).exists()


@pytest.mark.django_db
def test_importacao_aplica_webp_256_com_caminho_content_addressed(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    character = CharacterFactory(stable_id="tokai-teio")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "tokai.png").write_bytes(image_bytes(size=(400, 300)))
    manifest = write_manifest(
        tmp_path,
        "tokai-teio,tokai.png,curadoria-local,,Acervo local autorizado,true\n",
    )

    report = import_images(manifest, source_dir, dry_run=False)

    assert not report.errors
    asset = ImageAsset.objects.get(character=character, is_current=True)
    assert asset.status == ImageAsset.Status.VALID
    assert asset.width == 256
    assert asset.height == 256
    assert asset.file_path == f"characters/tokai-teio/{asset.checksum_sha256}.webp"
    saved = settings.MEDIA_ROOT / asset.file_path
    assert saved.exists()
    with Image.open(saved) as image:
        assert image.format == "WEBP"
        assert image.size == (256, 256)


@pytest.mark.django_db
def test_substituicao_preserva_imagem_anterior(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    character = CharacterFactory(stable_id="tokai-teio")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "primeira.png").write_bytes(image_bytes(color=(255, 0, 0)))
    (source_dir / "segunda.png").write_bytes(image_bytes(color=(0, 255, 0)))
    manifest = write_manifest(
        tmp_path,
        "tokai-teio,primeira.png,curadoria-local,,Local,true\n",
    )
    import_images(manifest, source_dir, dry_run=False)

    manifest = write_manifest(
        tmp_path,
        "tokai-teio,segunda.png,curadoria-local,,Local,true\n",
    )
    report = import_images(manifest, source_dir, dry_run=False)

    assert report.replaced == 1
    current = ImageAsset.objects.filter(character=character, is_current=True)
    assert current.count() == 1
    assert ImageAsset.objects.filter(character=character).count() == 2
    assert (settings.MEDIA_ROOT / current.get().file_path).exists()


@pytest.mark.django_db
def test_fonte_externa_exige_nota_de_licenca(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    CharacterFactory(stable_id="tokai-teio")
    CatalogSourceFactory(name="gametora")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "tokai.png").write_bytes(image_bytes())
    manifest = write_manifest(
        tmp_path,
        "tokai-teio,tokai.png,gametora,https://exemplo.test/tokai,,true\n",
    )

    report = import_images(manifest, source_dir, dry_run=False)

    assert report.errors
    assert "license_note" in report.errors[0].message
    assert not ImageAsset.objects.exists()


@pytest.mark.django_db
def test_caminho_fora_do_diretorio_de_origem_e_rejeitado(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    CharacterFactory(stable_id="tokai-teio")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (tmp_path / "segredo.png").write_bytes(image_bytes())
    manifest = write_manifest(
        tmp_path,
        "tokai-teio,../segredo.png,curadoria-local,,Local,true\n",
    )

    report = import_images(manifest, source_dir, dry_run=False)

    assert report.errors
    assert "inválido" in report.errors[0].message.lower()


@pytest.mark.django_db
def test_checksum_duplicado_entre_personagens_gera_aviso(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path / "media"
    CharacterFactory(stable_id="tokai-teio")
    CharacterFactory(stable_id="special-week")
    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / "igual.png").write_bytes(image_bytes())
    manifest = write_manifest(
        tmp_path,
        "tokai-teio,igual.png,curadoria-local,,Local,true\n"
        "special-week,igual.png,curadoria-local,,Local,true\n",
    )

    report = import_images(manifest, source_dir, dry_run=False)

    assert not report.errors
    assert report.warnings
    assert ImageAsset.objects.count() == 2


@pytest.mark.django_db
def test_validate_all_images_detecta_orfaos_e_personagens_sem_imagem(tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    character = CharacterFactory(stable_id="com-imagem")
    CharacterFactory(stable_id="sem-imagem")
    file_path = "characters/com-imagem/ok.webp"
    target = tmp_path / file_path
    target.parent.mkdir(parents=True)
    target.write_bytes(image_bytes())
    ImageAssetFactory(character=character, file_path=file_path, checksum_sha256="")
    orphan = tmp_path / "characters/orfao.webp"
    orphan.write_bytes(image_bytes())

    report = validate_all_images()

    assert report.valid == 1
    assert "characters/orfao.webp" in report.orphans
    assert "sem-imagem" in report.characters_without_image
    assert "com-imagem" not in report.characters_without_image
