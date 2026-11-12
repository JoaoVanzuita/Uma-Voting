"""Sincronização híbrida do catálogo e revisão de mudanças."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from django.db import transaction
from django.utils import timezone

from apps.catalog.models import (
    Aptitude,
    CatalogSource,
    Character,
    CharacterVersion,
    CharacterVersionAptitude,
    SyncChange,
    SyncRun,
)
from apps.catalog.services.importers import (
    CatalogCharacter,
    CatalogParseReport,
    ImportIssue,
    parse_catalog_file,
)

logger = logging.getLogger("apps.catalog.sync")


class CatalogSyncError(Exception):
    """Falha de domínio na sincronização do catálogo."""


@dataclass
class PlannedChange:
    change_type: str
    character: Character | None
    version: CharacterVersion | None
    payload: dict
    auto_applied: bool = False


@dataclass
class SyncPreview:
    total_rows: int = 0
    new_characters: list[CatalogCharacter] = field(default_factory=list)
    pending_changes: list[PlannedChange] = field(default_factory=list)
    ignored_characters: list[CatalogCharacter] = field(default_factory=list)
    errors: list[ImportIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def _aptitude_values(payload: dict) -> set[tuple[str, str]]:
    values: set[tuple[str, str]] = set()
    for category, items in payload.items():
        for value in items or ():
            values.add((category, value))
    return values


def _resolve_aptitudes(payload: dict) -> list[Aptitude]:
    resolved: list[Aptitude] = []
    for category, values in payload.items():
        for value in values or ():
            try:
                resolved.append(Aptitude.objects.get(category=category, value=value))
            except Aptitude.DoesNotExist as exc:
                raise CatalogSyncError(f"Aptidão não cadastrada: {category}={value}.") from exc
    return resolved


def _set_version_aptitudes(version: CharacterVersion, payload: dict) -> None:
    aptitudes = _resolve_aptitudes(payload)
    CharacterVersionAptitude.objects.filter(version=version).delete()
    CharacterVersionAptitude.objects.bulk_create(
        [CharacterVersionAptitude(version=version, aptitude=aptitude) for aptitude in aptitudes]
    )


def _apply_version_payload(
    character: Character,
    version_payload: dict,
    source: CatalogSource | None,
) -> CharacterVersion:
    release_date = version_payload.get("release_date_global")
    if isinstance(release_date, str):
        release_date = date.fromisoformat(release_date) if release_date else None

    version, _created = CharacterVersion.objects.update_or_create(
        stable_id=version_payload["stable_id"],
        defaults={
            "character": character,
            "display_name": version_payload["display_name"],
            "release_date_global": release_date,
            "source": source,
        },
    )
    _set_version_aptitudes(version, version_payload.get("aptitudes", {}))
    return version


def _apply_new_character(
    payload: dict,
    source: CatalogSource | None,
) -> Character:
    character, _created = Character.objects.update_or_create(
        stable_id=payload["character_stable_id"],
        defaults={"display_name": payload["character_name"]},
    )
    for version_payload in payload.get("versions", []):
        _apply_version_payload(character, version_payload, source)
    return character


def _apply_update_character(change: SyncChange) -> None:
    character = change.character
    if character is None:
        raise CatalogSyncError("Mudança sem personagem associada.")
    character.display_name = change.payload["display_name"]
    character.save(update_fields=["display_name", "updated_at"])


def _apply_new_version(change: SyncChange) -> None:
    character = change.character
    if character is None:
        raise CatalogSyncError("Mudança sem personagem associada.")
    version = _apply_version_payload(character, change.payload["version"], change.sync_run.source)
    change.version = version


def _apply_update_version(change: SyncChange) -> None:
    version = change.version
    if version is None:
        raise CatalogSyncError("Mudança sem versão associada.")
    release_date = change.payload.get("release_date_global")
    if isinstance(release_date, str):
        release_date = date.fromisoformat(release_date) if release_date else None
    version.display_name = change.payload["display_name"]
    version.release_date_global = release_date
    version.save(update_fields=["display_name", "release_date_global", "updated_at"])


def _apply_aptitude_change(change: SyncChange) -> None:
    version = change.version
    if version is None:
        raise CatalogSyncError("Mudança sem versão associada.")
    _set_version_aptitudes(version, change.payload["aptitudes"])


def _apply_payload(change: SyncChange) -> None:
    if change.change_type == SyncChange.ChangeType.UPDATE_CHARACTER:
        _apply_update_character(change)
    elif change.change_type == SyncChange.ChangeType.NEW_VERSION:
        _apply_new_version(change)
    elif change.change_type == SyncChange.ChangeType.UPDATE_VERSION:
        _apply_update_version(change)
    elif change.change_type == SyncChange.ChangeType.APTITUDE_CHANGE:
        _apply_aptitude_change(change)
    else:
        raise CatalogSyncError(f"Tipo de mudança não aplicável: {change.change_type}.")


def _version_aptitude_values(version: CharacterVersion) -> set[tuple[str, str]]:
    return {
        (link.aptitude.category, link.aptitude.value)
        for link in CharacterVersionAptitude.objects.filter(version=version).select_related(
            "aptitude"
        )
    }


def _plan_changes(report: CatalogParseReport) -> tuple[list[PlannedChange], list[ImportIssue]]:
    planned: list[PlannedChange] = []
    errors: list[ImportIssue] = []

    for character_payload in report.characters.values():
        if not character_payload.has_global_release:
            continue

        existing = Character.objects.filter(stable_id=character_payload.stable_id).first()
        if existing is None:
            conflicts = CharacterVersion.objects.filter(
                stable_id__in=[row.version_stable_id for row in character_payload.versions]
            )
            for conflict in conflicts:
                errors.append(
                    ImportIssue(
                        None,
                        "version_stable_id",
                        f"Versão '{conflict.stable_id}' já pertence a outra personagem.",
                    )
                )
            if conflicts:
                continue
            planned.append(
                PlannedChange(
                    change_type=SyncChange.ChangeType.NEW_CHARACTER,
                    character=None,
                    version=None,
                    payload=character_payload.payload(),
                    auto_applied=True,
                )
            )
            continue

        if existing.display_name != character_payload.display_name:
            planned.append(
                PlannedChange(
                    change_type=SyncChange.ChangeType.UPDATE_CHARACTER,
                    character=existing,
                    version=None,
                    payload={"display_name": character_payload.display_name},
                )
            )

        existing_versions = {
            version.stable_id: version
            for version in CharacterVersion.objects.filter(character=existing)
        }

        for row in character_payload.versions:
            existing_version = existing_versions.get(row.version_stable_id)
            if existing_version is None:
                conflict = CharacterVersion.objects.filter(stable_id=row.version_stable_id).first()
                if conflict is not None and conflict.character_id != existing.pk:
                    errors.append(
                        ImportIssue(
                            row.line,
                            "version_stable_id",
                            f"Versão '{row.version_stable_id}' pertence a outra personagem.",
                        )
                    )
                    continue
                planned.append(
                    PlannedChange(
                        change_type=SyncChange.ChangeType.NEW_VERSION,
                        character=existing,
                        version=None,
                        payload={
                            "character_stable_id": existing.stable_id,
                            "version": row.payload(),
                        },
                    )
                )
                continue

            release_date = row.release_date_global
            if (
                existing_version.display_name != row.version_name
                or existing_version.release_date_global != release_date
            ):
                planned.append(
                    PlannedChange(
                        change_type=SyncChange.ChangeType.UPDATE_VERSION,
                        character=existing,
                        version=existing_version,
                        payload={
                            "version_stable_id": row.version_stable_id,
                            "display_name": row.version_name,
                            "release_date_global": (
                                release_date.isoformat() if release_date else None
                            ),
                        },
                    )
                )

            if _version_aptitude_values(existing_version) != _aptitude_values(row.aptitudes):
                planned.append(
                    PlannedChange(
                        change_type=SyncChange.ChangeType.APTITUDE_CHANGE,
                        character=existing,
                        version=existing_version,
                        payload={
                            "version_stable_id": row.version_stable_id,
                            "aptitudes": row.payload()["aptitudes"],
                        },
                    )
                )

    return planned, errors


def preview_catalog(report: CatalogParseReport) -> SyncPreview:
    """Calcula a prévia sem gravar no banco."""
    preview = SyncPreview(
        total_rows=report.total_rows,
        ignored_characters=report.ignored_characters,
        errors=list(report.errors),
    )
    if report.has_errors:
        return preview

    planned, errors = _plan_changes(report)
    preview.errors.extend(errors)
    if errors:
        return preview

    for change in planned:
        if change.auto_applied:
            preview.new_characters.append(
                CatalogCharacter(
                    stable_id=change.payload["character_stable_id"],
                    display_name=change.payload["character_name"],
                )
            )
        else:
            preview.pending_changes.append(change)
    return preview


def preview_catalog_file(path: str) -> SyncPreview:
    return preview_catalog(parse_catalog_file(path))


def _summary(report: CatalogParseReport, applied: int, pending: int, ignored: int) -> str:
    return (
        f"{report.total_rows} linha(s); {applied} personagem(ns) nova(s) aplicada(s); "
        f"{pending} mudança(s) pendente(s); {ignored} personagem(ns) ignorada(s)."
    )


def sync_from_file(
    path: str,
    source: CatalogSource,
    *,
    triggered_by=None,
) -> SyncRun:
    """Sincroniza o catálogo a partir de um arquivo CSV.

    Personagens novas são aplicadas automaticamente; alterações em personagens
    existentes ficam pendentes de aprovação administrativa.
    """
    return sync_from_report(
        parse_catalog_file(path),
        source,
        triggered_by=triggered_by,
    )


def _failed_run(
    report: CatalogParseReport,
    source: CatalogSource,
    *,
    triggered_by,
    origin: str,
    errors: list[ImportIssue],
) -> SyncRun:
    return SyncRun.objects.create(
        source=source,
        status=SyncRun.Status.FAILED,
        finished_at=timezone.now(),
        error_message="; ".join(issue.message for issue in errors),
        summary=_summary(report, 0, 0, 0),
        triggered_by=triggered_by,
        origin=origin,
    )


def sync_from_report(
    report: CatalogParseReport,
    source: CatalogSource,
    *,
    triggered_by=None,
    apply_all: bool = False,
    origin: str = SyncRun.Origin.MANUAL,
) -> SyncRun:
    """Aplica um relatório de catálogo já parseado.

    Com ``apply_all=False`` (fluxo CSV), alterações em personagens existentes
    ficam pendentes de revisão. Com ``apply_all=True`` (importação externa),
    todas as mudanças planejadas são aplicadas e registradas como
    ``SyncChange(status=auto_applied)``.
    """
    if report.has_errors:
        return _failed_run(
            report,
            source,
            triggered_by=triggered_by,
            origin=origin,
            errors=report.errors,
        )

    planned, plan_errors = _plan_changes(report)
    if plan_errors:
        return _failed_run(
            report,
            source,
            triggered_by=triggered_by,
            origin=origin,
            errors=plan_errors,
        )

    run = SyncRun.objects.create(
        source=source,
        status=SyncRun.Status.RUNNING,
        triggered_by=triggered_by,
        origin=origin,
    )

    applied = 0
    pending = 0
    ignored = len(report.ignored_characters)

    try:
        with transaction.atomic():
            for change in planned:
                if change.auto_applied:
                    character = _apply_new_character(change.payload, source)
                    SyncChange.objects.create(
                        sync_run=run,
                        change_type=change.change_type,
                        character=character,
                        payload=change.payload,
                        status=SyncChange.Status.AUTO_APPLIED,
                    )
                    applied += 1
                elif apply_all:
                    stored = SyncChange.objects.create(
                        sync_run=run,
                        change_type=change.change_type,
                        character=change.character,
                        version=change.version,
                        payload=change.payload,
                        status=SyncChange.Status.PENDING,
                    )
                    _apply_payload(stored)
                    stored.status = SyncChange.Status.AUTO_APPLIED
                    update_fields = ["status"]
                    if stored.version_id is not None:
                        update_fields.append("version")
                    stored.save(update_fields=update_fields)
                    applied += 1
                else:
                    SyncChange.objects.create(
                        sync_run=run,
                        change_type=change.change_type,
                        character=change.character,
                        version=change.version,
                        payload=change.payload,
                        status=SyncChange.Status.PENDING,
                    )
                    pending += 1

            run.status = SyncRun.Status.PARTIAL if pending else SyncRun.Status.SUCCESS
            run.finished_at = timezone.now()
            run.summary = _summary(report, applied, pending, ignored)
            run.save(update_fields=["status", "finished_at", "summary"])
    except Exception as exc:  # pragma: no cover - proteção de rollback
        logger.exception("Falha ao sincronizar catálogo")
        run.status = SyncRun.Status.FAILED
        run.finished_at = timezone.now()
        run.error_message = str(exc)
        run.summary = _summary(report, 0, 0, ignored)
        run.save(update_fields=["status", "finished_at", "error_message", "summary"])

    return run


def approve_change(change: SyncChange, admin) -> None:
    """Aprova uma mudança pendente aplicando o payload em transação única."""
    if change.status != SyncChange.Status.PENDING:
        raise CatalogSyncError("Somente mudanças pendentes podem ser aprovadas.")

    with transaction.atomic():
        locked = SyncChange.objects.select_for_update().get(pk=change.pk)
        if locked.status != SyncChange.Status.PENDING:
            raise CatalogSyncError("Somente mudanças pendentes podem ser aprovadas.")

        _apply_payload(locked)
        locked.status = SyncChange.Status.APPROVED
        locked.reviewed_by = admin
        locked.reviewed_at = timezone.now()
        locked.save(
            update_fields=[
                "status",
                "reviewed_by",
                "reviewed_at",
                "version",
            ]
        )


def reject_change(change: SyncChange, admin, note: str = "") -> None:
    """Rejeita uma mudança pendente, registrando revisor e nota."""
    if change.status != SyncChange.Status.PENDING:
        raise CatalogSyncError("Somente mudanças pendentes podem ser rejeitadas.")

    change.status = SyncChange.Status.REJECTED
    change.reviewed_by = admin
    change.reviewed_at = timezone.now()
    change.review_note = note
    change.save(update_fields=["status", "reviewed_by", "reviewed_at", "review_note"])
