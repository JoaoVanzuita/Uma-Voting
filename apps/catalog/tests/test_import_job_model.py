"""Invariantes de banco de `ImportJob`: constraints, índice parcial e triggers."""

from __future__ import annotations

import pytest
from django.db import DatabaseError, IntegrityError, transaction
from django.utils import timezone

from apps.catalog.models import CatalogSource, ImportJob
from tests.factories import CatalogSourceFactory, ImportJobFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def source() -> CatalogSource:
    return CatalogSourceFactory(adapter="fake-source")


def terminal_job(source, status=ImportJob.Status.SUCCESS):
    return ImportJobFactory(
        source=source,
        status=status,
        phase=ImportJob.Phase.FINISHED,
        finished_at=timezone.now(),
    )


# ---------------------------------------------------------------------------
# CheckConstraint
# ---------------------------------------------------------------------------
def test_kind_invalido_e_rejeitado(source):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ImportJob.objects.create(source=source, kind="invalido")


def test_status_invalido_e_rejeitado(source):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ImportJob.objects.create(source=source, kind="catalog", status="invalido")


def test_phase_invalida_e_rejeitada(source):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ImportJob.objects.create(source=source, kind="catalog", phase="invalido")


def test_progresso_nao_pode_exceder_total(source):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ImportJob.objects.create(
                source=source,
                kind="images",
                progress_total=1,
                progress_done=2,
            )


def test_estado_terminal_exige_finished_at_e_phase_finished(source):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ImportJob.objects.create(
                source=source,
                kind="catalog",
                status=ImportJob.Status.SUCCESS,
                phase=ImportJob.Phase.QUEUED,
            )


def test_estado_nao_terminal_nao_pode_ter_finished_at(source):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ImportJob.objects.create(
                source=source,
                kind="catalog",
                status=ImportJob.Status.RUNNING,
                phase=ImportJob.Phase.CATALOG,
                finished_at=timezone.now(),
            )


def test_cancelada_exige_autor_e_data(source):
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ImportJob.objects.create(
                source=source,
                kind="catalog",
                status=ImportJob.Status.CANCELLED,
                phase=ImportJob.Phase.FINISHED,
                finished_at=timezone.now(),
            )


# ---------------------------------------------------------------------------
# Índice único parcial
# ---------------------------------------------------------------------------
def test_apenas_uma_execucao_running(source):
    ImportJobFactory(
        source=source,
        status=ImportJob.Status.RUNNING,
        phase=ImportJob.Phase.CATALOG,
    )
    other = CatalogSourceFactory(adapter="fake-source")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ImportJobFactory(
                source=other,
                status=ImportJob.Status.RUNNING,
                phase=ImportJob.Phase.CATALOG,
            )


def test_estados_terminais_nao_contam_para_o_indice(source):
    terminal_job(source, ImportJob.Status.SUCCESS)
    terminal_job(source, ImportJob.Status.FAILED)

    assert ImportJob.objects.filter(source=source).count() == 2


# ---------------------------------------------------------------------------
# Triggers
# ---------------------------------------------------------------------------
def test_transicao_de_running_para_terminal_e_permitida(source):
    job = ImportJobFactory(
        source=source,
        status=ImportJob.Status.RUNNING,
        phase=ImportJob.Phase.CATALOG,
        started_at=timezone.now(),
    )

    job.status = ImportJob.Status.SUCCESS
    job.phase = ImportJob.Phase.FINISHED
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "phase", "finished_at"])

    job.refresh_from_db()
    assert job.status == ImportJob.Status.SUCCESS
    assert job.phase == ImportJob.Phase.FINISHED


def test_execucao_terminal_nao_pode_ser_alterada(source):
    job = terminal_job(source)

    with pytest.raises(DatabaseError, match="terminal"):
        with transaction.atomic():
            ImportJob.objects.filter(pk=job.pk).update(current_step="reaberta")


def test_execucao_terminal_nao_pode_voltar_para_running(source):
    job = terminal_job(source)

    with pytest.raises(DatabaseError, match="terminal"):
        with transaction.atomic():
            ImportJob.objects.filter(pk=job.pk).update(
                status=ImportJob.Status.RUNNING,
                phase=ImportJob.Phase.CATALOG,
                finished_at=None,
            )


def test_execucao_nao_pode_ser_removida(source):
    job = terminal_job(source)

    with pytest.raises(DatabaseError, match="removida"):
        with transaction.atomic():
            job.delete()
