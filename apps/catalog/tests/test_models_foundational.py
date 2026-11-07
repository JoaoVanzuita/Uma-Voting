"""Testes fundamentais dos modelos de catálogo e dos dados iniciais."""

import pytest
from django.db import IntegrityError, transaction

from apps.catalog.models import (
    Aptitude,
    CatalogSource,
    CharacterVersion,
    CharacterVersionAptitude,
    ImageAsset,
)
from tests.factories import (
    AptitudeFactory,
    CharacterVersionAptitudeFactory,
    CharacterVersionFactory,
    ImageAssetFactory,
)


@pytest.mark.django_db
def test_data_migration_cria_as_dez_aptidoes():
    assert Aptitude.objects.count() == 10
    assert set(Aptitude.objects.values_list("category", flat=True)) == {
        "strategy",
        "distance",
        "surface",
    }


@pytest.mark.django_db
def test_data_migration_cria_fonte_curadoria_local():
    source = CatalogSource.objects.get(name="curadoria-local")

    assert source.kind == "file"
    assert source.enabled is True


@pytest.mark.django_db
def test_aptitude_unica_por_categoria_valor():
    AptitudeFactory(category="strategy", value="teste-unico", label="Teste")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Aptitude.objects.create(
                category="strategy",
                value="teste-unico",
                label="Duplicada",
            )


@pytest.mark.django_db
def test_version_stable_id_unico_globalmente():
    existing = CharacterVersionFactory(stable_id="version-unica")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CharacterVersion.objects.create(
                character=existing.character,
                stable_id="version-unica",
                display_name="Duplicada",
            )


@pytest.mark.django_db
def test_associacao_version_aptidao_unica():
    link = CharacterVersionAptitudeFactory()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CharacterVersionAptitude.objects.create(
                version=link.version,
                aptitude=link.aptitude,
            )


@pytest.mark.django_db
def test_apenas_uma_imagem_corrente_por_personagem():
    current = ImageAssetFactory(is_current=True)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ImageAsset.objects.create(
                character=current.character,
                file_path="characters/other/image.webp",
                is_current=True,
                status=ImageAsset.Status.VALID,
                checksum_sha256="a" * 64,
                width=256,
                height=256,
            )


@pytest.mark.django_db
def test_imagens_historicas_nao_conflitam_com_a_corrente():
    current = ImageAssetFactory(is_current=True)

    historical = ImageAssetFactory(
        character=current.character,
        is_current=False,
        file_path="characters/other/historical.webp",
    )

    assert historical.is_current is False


@pytest.mark.django_db
def test_dimensoes_de_imagem_devem_ser_positivas():
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ImageAssetFactory(width=0)
