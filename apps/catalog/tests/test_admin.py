"""Testes de integração do admin de catálogo."""

from __future__ import annotations

from datetime import date

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.catalog.models import (
    Aptitude,
    CatalogSource,
    Character,
    CharacterVersionAptitude,
    ImageAsset,
    SyncChange,
    SyncRun,
)
from tests.factories import (
    AdminUserFactory,
    CharacterFactory,
    CharacterVersionFactory,
    ImageAssetFactory,
    ParticipantFactory,
)

HEADER = (
    "character_stable_id,character_name,version_stable_id,version_name,"
    "release_date_global,strategy,distances,surfaces\n"
)


def catalog_upload(body: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(
        "catalog.csv",
        (HEADER + body).encode("utf-8"),
        content_type="text/csv",
    )


@pytest.mark.django_db
def test_status_exige_administrador(client):
    participant = ParticipantFactory()
    client.force_login(participant)

    response = client.get(reverse("admin:catalog_status"))

    assert response.status_code == 403


@pytest.mark.django_db
def test_status_exibe_estado_do_catalogo(client):
    admin = AdminUserFactory()
    CharacterFactory(display_name="Tokai Teio")
    client.force_login(admin)

    response = client.get(reverse("admin:catalog_status"))

    assert response.status_code == 200
    assert "Catálogo" in response.content.decode()
    assert "Sincronização manual" in response.content.decode()


@pytest.mark.django_db
def test_sincronizacao_manual_cria_run_e_redireciona(client):
    admin = AdminUserFactory()
    client.force_login(admin)

    response = client.post(
        reverse("admin:catalog_sync"),
        {
            "source": CatalogSource.objects.get(name="curadoria-local").pk,
            "file": catalog_upload(
                "tokai-teio,Tokai Teio,original,Original,2025-06-26,pace,medium,turf\n"
            ),
        },
    )

    run = SyncRun.objects.get()
    assert response.status_code == 302
    assert response.url == reverse("admin:catalog_sync_detail", args=[run.pk])
    assert Character.objects.filter(stable_id="tokai-teio").exists()


@pytest.mark.django_db
def test_detalhe_lista_mudancas_pendentes(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    version = CharacterVersionFactory(
        character=character,
        stable_id="original",
        release_date_global=date(2025, 6, 26),
    )
    CharacterVersionAptitude.objects.create(
        version=version,
        aptitude=Aptitude.objects.get(category="strategy", value="pace"),
    )
    client.post(
        reverse("admin:catalog_sync"),
        {
            "source": CatalogSource.objects.get(name="curadoria-local").pk,
            "file": catalog_upload(
                "tokai-teio,Tokai Teio Renomeada,original,Original,"
                "2025-06-26,pace,medium,turf\n"
            ),
        },
    )
    run = SyncRun.objects.get()
    change = run.changes.get(change_type=SyncChange.ChangeType.UPDATE_CHARACTER)

    response = client.get(reverse("admin:catalog_sync_detail", args=[run.pk]))

    assert response.status_code == 200
    body = response.content.decode()
    assert "Tokai Teio Renomeada" in body
    assert "Aprovar" in body
    assert reverse("admin:catalog_approve", args=[change.pk]) in body


@pytest.mark.django_db
def test_aprovacao_pelo_admin_aplica_mudanca(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    CharacterVersionFactory(
        character=character,
        stable_id="original",
        release_date_global=date(2025, 6, 26),
    )
    client.post(
        reverse("admin:catalog_sync"),
        {
            "source": CatalogSource.objects.get(name="curadoria-local").pk,
            "file": catalog_upload(
                "tokai-teio,Tokai Teio Renomeada,original,Original,"
                "2025-06-26,pace,medium,turf\n"
            ),
        },
    )
    change = SyncChange.objects.get(change_type=SyncChange.ChangeType.UPDATE_CHARACTER)

    response = client.post(reverse("admin:catalog_approve", args=[change.pk]))

    change.refresh_from_db()
    character.refresh_from_db()
    assert response.status_code == 302
    assert change.status == SyncChange.Status.APPROVED
    assert change.reviewed_by == admin
    assert character.display_name == "Tokai Teio Renomeada"


@pytest.mark.django_db
def test_rejeicao_pelo_admin_registra_nota(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    client.post(
        reverse("admin:catalog_sync"),
        {
            "source": CatalogSource.objects.get(name="curadoria-local").pk,
            "file": catalog_upload(
                "tokai-teio,Tokai Teio,nova,Nova,2025-06-26,pace,medium,turf\n"
            ),
        },
    )
    change = SyncChange.objects.get()

    response = client.post(
        reverse("admin:catalog_reject", args=[change.pk]),
        {"note": "aguardando revisão"},
    )

    change.refresh_from_db()
    assert response.status_code == 302
    assert change.status == SyncChange.Status.REJECTED
    assert change.review_note == "aguardando revisão"


@pytest.mark.django_db
def test_personagens_lista_aptidoes_consolidadas(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    version = CharacterVersionFactory(
        character=character,
        stable_id="original",
        release_date_global=date(2025, 6, 26),
    )
    CharacterVersionAptitude.objects.create(
        version=version,
        aptitude=Aptitude.objects.get(category="strategy", value="pace"),
    )

    response = client.get(reverse("admin:catalog_characters"))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Tokai Teio" in body
    assert "pace" in body


@pytest.mark.django_db
def test_imagens_lista_assets_e_valida_acervo(client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = AdminUserFactory()
    client.force_login(admin)
    CharacterFactory(stable_id="sem-imagem", display_name="Sem Imagem")
    asset = ImageAssetFactory(
        character=CharacterFactory(stable_id="com-imagem", display_name="Com Imagem"),
        file_path="characters/com-imagem/ok.webp",
        status=ImageAsset.Status.MISSING,
    )

    response = client.get(reverse("admin:catalog_images"))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Sem Imagem" in body
    assert "Com Imagem" in body

    response = client.post(reverse("admin:catalog_images_validate"))

    assert response.status_code == 200
    assert "Relatório de validação" in response.content.decode()
    asset.refresh_from_db()
    assert asset.status == ImageAsset.Status.MISSING
