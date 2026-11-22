"""Storage de mídia via Storage API: filesystem e S3 simulado."""

from __future__ import annotations

import hashlib
import io

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.template import Context, Template
from PIL import Image

from apps.catalog.models import ImageAsset
from apps.catalog.services import media
from apps.catalog.services.images import (
    store_image_bytes,
    validate_all_images,
    validate_image_asset,
)
from tests.factories import CatalogSourceFactory, CharacterFactory, ImageAssetFactory


def image_bytes(size=(256, 256), color=(30, 90, 150)) -> bytes:
    image = Image.new("RGB", size, color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


class FakeS3Storage(Storage):
    """Simula um bucket privado: sem filesystem, URLs assinadas e listagem por prefixo."""

    signed_url = "https://bucket.example/{name}?X-Amz-Signature=abc"

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.listdir_calls = 0

    def exists(self, name):
        return name in self.files

    def open(self, name, mode="rb"):
        if name not in self.files:
            raise FileNotFoundError(name)
        return ContentFile(self.files[name])

    def save(self, name, content, max_length=None):
        self.files[name] = content.read()
        return name

    def url(self, name):
        return self.signed_url.format(name=name)

    def listdir(self, path):
        self.listdir_calls += 1
        prefix = f"{path}/" if path else ""
        directories: set[str] = set()
        files: list[str] = []
        for name in self.files:
            if not name.startswith(prefix):
                continue
            remainder = name[len(prefix) :]
            if "/" in remainder:
                directories.add(remainder.split("/", 1)[0])
            else:
                files.append(remainder)
        return sorted(directories), sorted(files)


@pytest.fixture
def fake_s3(monkeypatch):
    storage = FakeS3Storage()
    monkeypatch.setattr(media, "get_storage", lambda: storage)
    media.clear_cache()
    yield storage
    media.clear_cache()


def test_s3_grava_le_e_lista_sem_filesystem(fake_s3):
    name = media.save_bytes("characters/a/x.webp", b"conteudo", content_type="image/webp")

    assert name == "characters/a/x.webp"
    assert media.exists(name)
    assert media.read_bytes(name) == b"conteudo"
    assert media.asset_url(name) == fake_s3.url(name)
    assert media.list_character_objects(refresh=True) == [name]


@pytest.mark.django_db
def test_s3_validacao_marca_ausente_e_valida_checksum(fake_s3):
    character = CharacterFactory(stable_id="tokai-teio")
    data = image_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    name = f"characters/tokai-teio/{checksum}.webp"
    fake_s3.files[name] = data
    asset = ImageAssetFactory(
        character=character,
        file_path=name,
        checksum_sha256=checksum,
        is_current=True,
    )

    result = validate_image_asset(asset)

    assert result.status == ImageAsset.Status.VALID
    assert result.checksum == checksum

    missing = ImageAssetFactory(file_path="characters/tokai-teio/ausente.webp")
    assert validate_image_asset(missing).status == ImageAsset.Status.MISSING


@pytest.mark.django_db
def test_s3_store_image_bytes_nao_duplica_objeto_existente(fake_s3):
    character = CharacterFactory(stable_id="special-week")
    source = CatalogSourceFactory(name="curadoria-local")

    first = store_image_bytes(character, image_bytes(), source=source)
    second = store_image_bytes(character, image_bytes(), source=source)

    assert first.destination == second.destination
    assert list(fake_s3.files) == [first.destination]


@pytest.mark.django_db
def test_s3_validate_all_images_detecta_orfaos_em_poucas_listagens(fake_s3):
    character = CharacterFactory(stable_id="com-imagem")
    data = image_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    name = f"characters/com-imagem/{checksum}.webp"
    fake_s3.files[name] = data
    fake_s3.files["characters/orfao.webp"] = data
    ImageAssetFactory(
        character=character,
        file_path=name,
        checksum_sha256=checksum,
        status=ImageAsset.Status.VALID,
    )

    report = validate_all_images()

    assert "characters/orfao.webp" in report.orphans
    assert report.valid == 1
    # Uma listagem por diretório (profundidade fixa), nunca um exists() por asset.
    assert fake_s3.listdir_calls <= 2


@pytest.mark.django_db
def test_template_usa_url_do_storage(fake_s3):
    data = image_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    name = f"characters/tokai-teio/{checksum}.webp"
    fake_s3.files[name] = data
    asset = ImageAssetFactory(
        file_path=name,
        status=ImageAsset.Status.VALID,
        checksum_sha256=checksum,
    )

    rendered = Template("{% load catalog_tags %}{% character_image asset %}").render(
        Context({"asset": asset})
    )

    assert rendered == fake_s3.url(name)


@pytest.mark.django_db
def test_ui_tags_usa_url_do_storage(fake_s3):
    data = image_bytes()
    checksum = hashlib.sha256(data).hexdigest()
    name = f"characters/tokai-teio/{checksum}.webp"
    fake_s3.files[name] = data
    asset = ImageAssetFactory(file_path=name, status=ImageAsset.Status.VALID)

    rendered = Template("{% load ui_tags %}{% image_url asset %}").render(Context({"asset": asset}))

    assert rendered == fake_s3.url(name)


@pytest.mark.django_db
def test_asset_invalido_usa_placeholder(fake_s3):
    asset = ImageAssetFactory(file_path="characters/x/x.webp", status=ImageAsset.Status.INVALID)

    rendered = Template("{% load ui_tags %}{% image_url asset %}").render(Context({"asset": asset}))

    assert rendered.startswith("/static/img/character-placeholder")


def test_url_quebrada_cai_no_placeholder(monkeypatch):
    class BrokenStorage(FakeS3Storage):
        def url(self, name):
            raise ValueError("sem URL pública")

    monkeypatch.setattr(media, "get_storage", lambda: BrokenStorage())

    assert media.asset_url("characters/x/y.webp") == ""
