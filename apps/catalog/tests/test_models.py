"""Testes de modelos e constraints do catálogo (Fase 6)."""

import pytest
from django.db.models import ProtectedError

from apps.catalog.models import SyncChange, SyncRun
from tests.factories import CatalogSourceFactory, CharacterFactory


@pytest.mark.django_db
def test_sync_run_inicia_em_execucao_e_registra_historico():
    source = CatalogSourceFactory()

    run = SyncRun.objects.create(source=source)

    assert run.status == SyncRun.Status.RUNNING
    assert run.started_at is not None
    assert run.finished_at is None
    assert run.triggered_by is None


@pytest.mark.django_db
def test_sync_run_nao_pode_ser_apagada_com_mudancas():
    run = SyncRun.objects.create(source=CatalogSourceFactory())
    SyncChange.objects.create(
        sync_run=run,
        change_type=SyncChange.ChangeType.UPDATE_CHARACTER,
        payload={"display_name": "Novo"},
    )

    with pytest.raises(ProtectedError):
        run.delete()


@pytest.mark.django_db
def test_fonte_protegida_por_execucao_de_sincronizacao():
    source = CatalogSourceFactory()
    SyncRun.objects.create(source=source)

    with pytest.raises(ProtectedError):
        source.delete()


@pytest.mark.django_db
def test_sync_change_padrao_pendente_e_payload_json():
    run = SyncRun.objects.create(source=CatalogSourceFactory())
    character = CharacterFactory()

    change = SyncChange.objects.create(
        sync_run=run,
        change_type=SyncChange.ChangeType.APTITUDE_CHANGE,
        character=character,
        payload={"aptitudes": {"strategy": ["pace"]}},
    )

    change.refresh_from_db()
    assert change.status == SyncChange.Status.PENDING
    assert change.payload == {"aptitudes": {"strategy": ["pace"]}}
    assert change.reviewed_by is None


@pytest.mark.django_db
def test_sync_changes_ordenadas_da_mais_recente_para_a_mais_antiga():
    run = SyncRun.objects.create(source=CatalogSourceFactory())
    first = SyncChange.objects.create(
        sync_run=run,
        change_type=SyncChange.ChangeType.UPDATE_CHARACTER,
        payload={"display_name": "A"},
    )
    second = SyncChange.objects.create(
        sync_run=run,
        change_type=SyncChange.ChangeType.UPDATE_CHARACTER,
        payload={"display_name": "B"},
    )

    assert list(SyncChange.objects.values_list("pk", flat=True)) == [second.pk, first.pk]
