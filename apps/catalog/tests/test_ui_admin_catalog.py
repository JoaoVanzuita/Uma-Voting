"""Contratos de apresentação do catálogo e imagens (Fase 5)."""

from __future__ import annotations

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import (
    Character,
    ImageAsset,
    SyncChange,
    SyncRun,
)
from tests.factories import (
    AdminUserFactory,
    CatalogSourceFactory,
    CharacterFactory,
    CharacterVersionFactory,
    ImageAssetFactory,
)

pytestmark = pytest.mark.django_db


def _login(client, user):
    client.force_login(user)
    return client


def test_status_exibe_ultima_sincronizacao_e_alteracoes_pendentes(client):
    admin = AdminUserFactory()
    source = CatalogSourceFactory(name="curadoria-local")
    run = SyncRun.objects.create(
        source=source,
        status=SyncRun.Status.PARTIAL,
        summary="1 linha(s); 1 mudança(s) pendente(s).",
    )
    character = CharacterFactory(display_name="Tokai Teio")
    SyncChange.objects.create(
        sync_run=run,
        change_type=SyncChange.ChangeType.UPDATE_CHARACTER,
        character=character,
        payload={"display_name": "Tokai Teio Renomeada"},
        status=SyncChange.Status.PENDING,
    )
    _login(client, admin)

    response = client.get(reverse("admin:catalog_status"))
    html = response.content.decode()

    assert response.status_code == 200
    assert "Sincronização manual" in html
    assert "Última sincronização" in html
    assert "Alterações pendentes" in html
    assert "stat-card__hint" not in html
    assert "section-header__index" not in html
    assert "Tokai Teio" in html
    assert reverse("admin:catalog_sync") in html
    assert reverse("admin:catalog_sync_detail", args=[run.pk]) in html
    assert 'data-label="Criada em"' in html


def test_detalhe_de_sincronizacao_separa_status_e_diferencas(client):
    admin = AdminUserFactory()
    source = CatalogSourceFactory(name="curadoria-local")
    run = SyncRun.objects.create(source=source, status=SyncRun.Status.PARTIAL)
    character = CharacterFactory(display_name="Tokai Teio")
    version = CharacterVersionFactory(character=character, display_name="Original")
    pending = SyncChange.objects.create(
        sync_run=run,
        change_type=SyncChange.ChangeType.UPDATE_CHARACTER,
        character=character,
        payload={"display_name": "Tokai Teio Renomeada"},
        status=SyncChange.Status.PENDING,
    )
    approved = SyncChange.objects.create(
        sync_run=run,
        change_type=SyncChange.ChangeType.APTITUDE_CHANGE,
        character=character,
        version=version,
        payload={"version_stable_id": version.stable_id, "aptitudes": {"strategy": ["pace"]}},
        status=SyncChange.Status.APPROVED,
        reviewed_by=admin,
        reviewed_at=timezone.now(),
        review_note="Aprovada na revisão.",
    )
    rejected = SyncChange.objects.create(
        sync_run=run,
        change_type=SyncChange.ChangeType.UPDATE_VERSION,
        character=character,
        version=version,
        payload={"display_name": "Nova versão", "release_date_global": None},
        status=SyncChange.Status.REJECTED,
    )
    _login(client, admin)

    response = client.get(reverse("admin:catalog_sync_detail", args=[run.pk]))
    html = response.content.decode()

    assert response.status_code == 200
    assert "Resumo da execução" in html
    assert "Alterações pendentes" in html
    assert "Alterações aprovadas" in html
    assert "Alterações rejeitadas" in html
    assert "Antes" in html
    assert "Depois" in html
    assert "change-diff" in html
    assert "Aprovar esta mudança e aplicá-la ao catálogo?" in html
    assert "Tokai Teio Renomeada" in html
    assert "Dados propostos" in html
    assert reverse("admin:catalog_approve", args=[pending.pk]) in html
    assert reverse("admin:catalog_reject", args=[pending.pk]) in html
    assert f'id="note-{pending.pk}"' in html
    assert reverse("admin:catalog_approve", args=[approved.pk]) not in html
    assert reverse("admin:catalog_reject", args=[rejected.pk]) not in html


def test_personagens_preserva_corte_inicial_e_paginacao(client):
    admin = AdminUserFactory()
    for index in range(51):
        CharacterFactory(
            stable_id=f"personagem-{index:03d}",
            display_name=f"Personagem {index:03d}",
        )
    _login(client, admin)

    response = client.get(reverse("admin:catalog_characters"))
    html = response.content.decode()

    assert response.status_code == 200
    assert 'value="2026-12-01"' in html
    assert "Página 1 de 2" in html
    assert "cutoff=2026-12-01" in html
    assert "page=2" in html
    assert 'data-label="Versões disponíveis"' in html
    assert 'data-label="Aptidões consolidadas"' in html
    assert Character.objects.count() == 51


def test_imagens_filtro_relatorio_e_miniaturas_controladas(client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    admin = AdminUserFactory()
    valid = ImageAssetFactory(
        character=CharacterFactory(stable_id="com-imagem", display_name="Com Imagem"),
        status=ImageAsset.Status.VALID,
    )
    missing = ImageAssetFactory(
        character=CharacterFactory(stable_id="sem-imagem-valida", display_name="Sem Imagem Válida"),
        status=ImageAsset.Status.MISSING,
    )
    CharacterFactory(stable_id="sem-asset", display_name="Sem Asset")
    _login(client, admin)

    response = client.get(reverse("admin:catalog_images"))
    html = response.content.decode()

    assert response.status_code == 200
    assert 'id="image-status"' in html
    assert "data-image-filter" in html
    assert 'data-image-status="valid"' in html
    assert 'data-image-status="missing"' in html
    assert 'width="48"' in html
    assert 'height="48"' in html
    assert "data-fallback-src" in html
    assert "character-thumb" in html
    assert "stat-card__hint" in html
    assert "Exibindo até 500 registros" in html
    assert "Sem Asset" in html

    filtered = client.get(reverse("admin:catalog_images"), {"status": "missing"})
    filtered_html = filtered.content.decode()
    assert '<option value="missing" selected>' in filtered_html
    assert f'data-image-status="{missing.status}"' in filtered_html
    assert 'data-image-status="valid"' not in filtered_html

    validation = client.post(reverse("admin:catalog_images_validate"))
    report_html = validation.content.decode()
    assert validation.status_code == 200
    assert "Relatório de validação" in report_html
    assert "asset(s) verificado(s)" in report_html
    assert valid.file_path in report_html
