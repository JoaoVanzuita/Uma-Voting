"""Testes do parser e da sincronização híbrida do catálogo."""

from __future__ import annotations

import io
from datetime import date

import pytest

from apps.catalog.models import (
    Aptitude,
    Character,
    CharacterVersionAptitude,
    SyncChange,
    SyncRun,
)
from apps.catalog.services.importers import parse_catalog_csv
from apps.catalog.services.queries import (
    consolidated_aptitude_values,
    eligible_characters,
    eligible_versions,
)
from apps.catalog.services.sync import (
    approve_change,
    preview_catalog,
    reject_change,
    sync_from_file,
    sync_from_report,
)
from tests.factories import (
    AdminUserFactory,
    CatalogSourceFactory,
    CharacterFactory,
    CharacterVersionFactory,
)

HEADER = (
    "character_stable_id,character_name,version_stable_id,version_name,"
    "release_date_global,strategy,distances,surfaces\n"
)


def write_catalog(tmp_path, body: str) -> str:
    path = tmp_path / "catalog.csv"
    path.write_text(HEADER + body, encoding="utf-8")
    return str(path)


def csv_file(body: str):
    return io.BytesIO((HEADER + body).encode("utf-8"))


def test_parser_valida_colunas_e_aptidoes():
    report = parse_catalog_csv(
        csv_file(
            "tokai-teio,Tokai Teio,tokai-teio-original,Tokai Teio (Original),"
            "2025-06-26,pace,medium;long,turf\n"
        )
    )

    assert not report.has_errors
    assert report.total_rows == 1
    row = report.rows[0]
    assert row.character_stable_id == "tokai-teio"
    assert row.release_date_global == date(2025, 6, 26)
    assert row.distances == ("medium", "long")
    assert row.aptitudes["surface"] == ("turf",)


def test_parser_rejeita_estrategia_invalida_e_data_invalida():
    report = parse_catalog_csv(
        csv_file("tokai-teio,Tokai Teio,tokai-teio-original,Original,26/06/2025,Pace,medium,turf\n")
    )

    assert report.has_errors
    fields = {issue.field for issue in report.errors}
    assert "release_date_global" in fields
    assert "strategy" in fields


def test_parser_rejeita_version_stable_id_duplicado():
    report = parse_catalog_csv(
        csv_file(
            "tokai-teio,Tokai Teio,dup,Original,2025-06-26,pace,medium,turf\n"
            "special-week,Special Week,dup,Original,2025-06-26,pace,medium,turf\n"
        )
    )

    assert any(issue.field == "version_stable_id" for issue in report.errors)


@pytest.mark.django_db
def test_nova_personagem_e_aplicada_automaticamente(tmp_path):
    source = CatalogSourceFactory(name="curadoria-local")
    path = write_catalog(
        tmp_path,
        "tokai-teio,Tokai Teio,tokai-teio-original,Tokai Teio (Original),"
        "2025-06-26,pace,medium;long,turf\n"
        "tokai-teio,Tokai Teio,tokai-teio-peak-joy,Tokai Teio (Peak Joy),"
        "2025-07-24,pace,mile;medium,turf\n",
    )

    run = sync_from_file(path, source)

    assert run.status == SyncRun.Status.SUCCESS
    character = Character.objects.get(stable_id="tokai-teio")
    assert character.display_name == "Tokai Teio"
    assert character.versions.count() == 2
    assert CharacterVersionAptitude.objects.filter(version__character=character).count() == 8
    change = SyncChange.objects.get(sync_run=run)
    assert change.status == SyncChange.Status.AUTO_APPLIED
    assert change.change_type == SyncChange.ChangeType.NEW_CHARACTER


@pytest.mark.django_db
def test_alteracao_existente_fica_pendente_sem_alterar_catalogo(tmp_path):
    source = CatalogSourceFactory(name="curadoria-local")
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    version = CharacterVersionFactory(
        character=character,
        stable_id="tokai-teio-original",
        display_name="Original",
        release_date_global=date(2025, 6, 26),
    )
    for category, value in (
        ("strategy", "pace"),
        ("distance", "medium"),
        ("surface", "turf"),
    ):
        CharacterVersionAptitude.objects.create(
            version=version,
            aptitude=Aptitude.objects.get(category=category, value=value),
        )

    path = write_catalog(
        tmp_path,
        "tokai-teio,Tokai Teio Renomeada,tokai-teio-original,Original,"
        "2025-06-26,pace,medium,turf\n"
        "tokai-teio,Tokai Teio Renomeada,tokai-teio-peak-joy,Peak Joy,"
        "2025-07-24,late,long,turf\n",
    )

    run = sync_from_file(path, source)

    assert run.status == SyncRun.Status.PARTIAL
    character.refresh_from_db()
    assert character.display_name == "Tokai Teio"
    assert character.versions.count() == 1
    pending = run.changes.filter(status=SyncChange.Status.PENDING)
    assert pending.count() == 2
    assert set(pending.values_list("change_type", flat=True)) == {
        SyncChange.ChangeType.UPDATE_CHARACTER,
        SyncChange.ChangeType.NEW_VERSION,
    }


@pytest.mark.django_db
def test_aprovacao_aplica_payload_e_registra_revisor(tmp_path):
    source = CatalogSourceFactory(name="curadoria-local")
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    CharacterVersionFactory(
        character=character,
        stable_id="tokai-teio-original",
        display_name="Original",
        release_date_global=date(2025, 6, 26),
    )
    path = write_catalog(
        tmp_path,
        "tokai-teio,Tokai Teio Renomeada,tokai-teio-original,Original,"
        "2025-06-26,pace,medium,turf\n",
    )
    run = sync_from_file(path, source)
    change = run.changes.get(change_type=SyncChange.ChangeType.UPDATE_CHARACTER)
    admin = AdminUserFactory()

    approve_change(change, admin)

    change.refresh_from_db()
    character.refresh_from_db()
    assert change.status == SyncChange.Status.APPROVED
    assert change.reviewed_by == admin
    assert character.display_name == "Tokai Teio Renomeada"


@pytest.mark.django_db
def test_rejeicao_registra_nota_sem_aplicar(tmp_path):
    source = CatalogSourceFactory(name="curadoria-local")
    CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    path = write_catalog(
        tmp_path,
        "tokai-teio,Tokai Teio Renomeada,tokai-teio-nova,Nova,2025-06-26,pace,medium,turf\n",
    )
    run = sync_from_file(path, source)
    change = run.changes.get(change_type=SyncChange.ChangeType.NEW_VERSION)
    admin = AdminUserFactory()

    reject_change(change, admin, "dados divergentes")

    change.refresh_from_db()
    assert change.status == SyncChange.Status.REJECTED
    assert change.review_note == "dados divergentes"
    assert Character.objects.get(stable_id="tokai-teio").versions.count() == 0


@pytest.mark.django_db
def test_personagem_sem_data_global_e_ignorada(tmp_path):
    source = CatalogSourceFactory(name="curadoria-local")
    path = write_catalog(
        tmp_path,
        "nao-lancada,Não Lançada,nao-lancada-original,Original,,pace,medium,turf\n",
    )

    run = sync_from_file(path, source)

    assert not Character.objects.filter(stable_id="nao-lancada").exists()
    assert run.status == SyncRun.Status.SUCCESS
    assert "1 personagem(ns) ignorada(s)" in run.summary


@pytest.mark.django_db
def test_arquivo_invalido_preserva_sync_run_e_nao_altera_catalogo(tmp_path):
    source = CatalogSourceFactory(name="curadoria-local")
    path = write_catalog(
        tmp_path,
        "tokai-teio,Tokai Teio,original,Original,2025-06-26,invalid,medium,turf\n",
    )

    run = sync_from_file(path, source)

    assert run.status == SyncRun.Status.FAILED
    assert run.error_message
    assert not Character.objects.exists()


@pytest.mark.django_db
def test_preview_nao_grava_nada(tmp_path):
    CatalogSourceFactory(name="curadoria-local")
    path = write_catalog(
        tmp_path,
        "tokai-teio,Tokai Teio,original,Original,2025-06-26,pace,medium,turf\n",
    )

    preview = preview_catalog(parse_catalog_csv(open(path, "rb")))

    assert len(preview.new_characters) == 1
    assert not preview.has_errors
    assert not Character.objects.exists()
    assert not SyncRun.objects.exists()


@pytest.mark.django_db
def test_consultas_de_elegibilidade_e_cutoff():
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    old = CharacterVersionFactory(
        character=character,
        stable_id="old",
        release_date_global=date(2025, 1, 1),
    )
    CharacterVersionFactory(
        character=character,
        stable_id="future",
        release_date_global=date(2027, 1, 1),
    )
    CharacterVersionAptitude.objects.create(
        version=old,
        aptitude=Aptitude.objects.get(category="strategy", value="pace"),
    )
    CharacterVersionAptitude.objects.create(
        version=old,
        aptitude=Aptitude.objects.get(category="distance", value="medium"),
    )

    cutoff = date(2026, 12, 1)
    assert list(eligible_versions(character, cutoff)) == [old]
    assert list(eligible_characters(cutoff)) == [character]
    assert consolidated_aptitude_values(character, cutoff) == {
        "distance": ["medium"],
        "strategy": ["pace"],
    }


@pytest.mark.django_db
def test_cutoff_exclui_personagem_sem_versao_lancada():
    CharacterFactory(stable_id="futura", display_name="Futura")

    assert not eligible_characters(date(2026, 12, 1)).exists()


# ---------------------------------------------------------------------------
# sync_from_report (importação externa)
# ---------------------------------------------------------------------------
def test_sync_from_report_modo_manual_mantem_alteracoes_pendentes(db):
    source = CatalogSourceFactory()
    CharacterFactory(stable_id="tokai-teio", display_name="Nome antigo")
    report = parse_catalog_csv(
        csv_file(
            "tokai-teio,Tokai Teio,tokai-teio-original,Tokai Teio (Original),"
            "2025-06-26,pace,medium;long,turf\n"
        )
    )

    run = sync_from_report(report, source)

    assert run.origin == SyncRun.Origin.MANUAL
    assert run.changes.filter(status=SyncChange.Status.PENDING).exists()
    assert not run.changes.filter(status=SyncChange.Status.AUTO_APPLIED).exists()


def test_sync_from_report_apply_all_nao_deixa_pendencias(db):
    source = CatalogSourceFactory()
    CharacterFactory(stable_id="tokai-teio", display_name="Nome antigo")
    report = parse_catalog_csv(
        csv_file(
            "tokai-teio,Tokai Teio,tokai-teio-original,Tokai Teio (Original),"
            "2025-06-26,pace,medium;long,turf\n"
        )
    )

    run = sync_from_report(
        report,
        source,
        apply_all=True,
        origin=SyncRun.Origin.EXTERNAL,
    )

    assert run.origin == SyncRun.Origin.EXTERNAL
    assert not run.changes.filter(status=SyncChange.Status.PENDING).exists()
    assert run.changes.filter(status=SyncChange.Status.AUTO_APPLIED).exists()
    assert Character.objects.get(stable_id="tokai-teio").display_name == "Tokai Teio"


def test_sync_from_report_apply_all_e_idempotente(db):
    source = CatalogSourceFactory()
    body = (
        "tokai-teio,Tokai Teio,tokai-teio-original,Tokai Teio (Original),"
        "2025-06-26,pace,medium;long,turf\n"
    )

    first = sync_from_report(
        parse_catalog_csv(csv_file(body)), source, apply_all=True, origin="external"
    )
    second = sync_from_report(
        parse_catalog_csv(csv_file(body)), source, apply_all=True, origin="external"
    )

    assert first.status == SyncRun.Status.SUCCESS
    assert second.status == SyncRun.Status.SUCCESS
    assert Character.objects.filter(stable_id="tokai-teio").count() == 1
    assert not second.changes.exists()
