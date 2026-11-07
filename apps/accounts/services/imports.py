"""Importação atômica de participantes por CSV."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field

from django.db import transaction

from apps.accounts.models import User
from apps.accounts.services.participants import ParticipantError, create_participant

MAX_FILE_SIZE = 1 * 1024 * 1024
CONTROL_CHARS = {chr(code) for code in range(32)} | {chr(127)}


@dataclass(frozen=True)
class ImportIssue:
    line: int | None
    value: str
    message: str


@dataclass
class ImportReport:
    total_lines: int = 0
    valid_rows: list[str] = field(default_factory=list)
    errors: list[ImportIssue] = field(default_factory=list)
    imported_count: int = 0
    applied: bool = False

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)


def _existing_usernames() -> set[str]:
    return {username.casefold() for username in User.objects.values_list("username", flat=True)}


def _validate_row(
    *,
    line: int,
    value: str,
    seen: set[str],
    existing: set[str],
) -> tuple[str | None, ImportIssue | None]:
    if not value:
        return None, ImportIssue(line, value, "Username vazio.")

    if len(value) > 150:
        return None, ImportIssue(
            line,
            value,
            "Username deve ter no máximo 150 caracteres.",
        )

    if any(character in CONTROL_CHARS for character in value):
        return None, ImportIssue(
            line,
            value,
            "Username contém caracteres de controle.",
        )

    key = value.casefold()
    if key in seen:
        return None, ImportIssue(
            line,
            value,
            "Username duplicado no arquivo.",
        )

    if key in existing:
        return None, ImportIssue(
            line,
            value,
            "Username já existe (comparação sem diferenciar maiúsculas).",
        )

    seen.add(key)
    return value, None


def parse_participants_csv(file_obj) -> ImportReport:
    """Valida o arquivo inteiro sem gravar nada."""
    report = ImportReport()

    try:
        data = file_obj.read()
    except Exception:
        report.errors.append(ImportIssue(None, "", "Não foi possível ler o arquivo."))
        return report

    if len(data) > MAX_FILE_SIZE:
        report.errors.append(ImportIssue(None, "", "Arquivo excede o limite de 1 MB."))
        return report

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        report.errors.append(ImportIssue(None, "", "Arquivo deve estar codificado em UTF-8."))
        return report

    if not text.strip():
        report.errors.append(ImportIssue(None, "", "Arquivo vazio."))
        return report

    try:
        rows = list(csv.reader(io.StringIO(text), strict=True))
    except csv.Error as exc:
        report.errors.append(ImportIssue(None, "", f"CSV inválido: {exc}."))
        return report

    seen: set[str] = set()
    existing = _existing_usernames()
    data_rows = [row for row in rows if any(cell.strip() for cell in row)]
    report.total_lines = len(data_rows)

    for index, row in enumerate(data_rows, start=1):
        if len(row) != 1:
            report.errors.append(
                ImportIssue(
                    index,
                    ",".join(row),
                    "Vírgula não suportada no username.",
                )
            )
            continue

        value = row[0].strip()
        if index == 1 and value.casefold() == "username":
            report.total_lines -= 1
            continue

        valid_value, issue = _validate_row(
            line=index,
            value=value,
            seen=seen,
            existing=existing,
        )
        if issue is not None:
            report.errors.append(issue)
        elif valid_value is not None:
            report.valid_rows.append(valid_value)

    if report.total_lines == 0:
        report.errors.append(ImportIssue(None, "", "Arquivo não contém usernames."))

    return report


def import_rows(
    rows: list[str],
    *,
    apply: bool,
    total_lines: int | None = None,
) -> ImportReport:
    """Revalida e aplica (ou simula) uma lista de usernames."""
    report = ImportReport(total_lines=total_lines or len(rows))
    seen: set[str] = set()
    existing = _existing_usernames()

    for index, raw_value in enumerate(rows, start=1):
        value = (raw_value or "").strip()
        valid_value, issue = _validate_row(
            line=index,
            value=value,
            seen=seen,
            existing=existing,
        )
        if issue is not None:
            report.errors.append(issue)
        elif valid_value is not None:
            report.valid_rows.append(valid_value)

    if report.has_errors or not apply:
        return report

    try:
        with transaction.atomic():
            for username in report.valid_rows:
                create_participant(username)
    except ParticipantError as exc:
        report.errors.append(ImportIssue(None, "", exc.message))
        report.valid_rows = []
        return report

    report.imported_count = len(report.valid_rows)
    report.applied = True
    return report


def import_participants(file_obj, *, apply: bool = False) -> ImportReport:
    """Valida o CSV e, quando aplicável, importa tudo em uma transação."""
    report = parse_participants_csv(file_obj)
    if report.has_errors:
        return report
    return import_rows(
        report.valid_rows,
        apply=apply,
        total_lines=report.total_lines,
    )
