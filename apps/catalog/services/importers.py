"""Parser e validador do catálogo curado em CSV.

Formato definido em ``contracts/import-formats.md`` §2. Nenhum scraping é
realizado no MVP: a importação de arquivo é o caminho operacional.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date

MAX_FILE_SIZE = 5 * 1024 * 1024
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

REQUIRED_COLUMNS = (
    "character_stable_id",
    "character_name",
    "version_stable_id",
    "version_name",
    "release_date_global",
    "strategy",
    "distances",
    "surfaces",
)

STRATEGIES = ("front", "pace", "late", "end")
DISTANCES = ("sprint", "mile", "medium", "long")
SURFACES = ("turf", "dirt")

APTITUDE_CATEGORIES = {
    "strategy": STRATEGIES,
    "distance": DISTANCES,
    "surface": SURFACES,
}


@dataclass(frozen=True)
class ImportIssue:
    line: int | None
    field: str
    message: str


@dataclass(frozen=True)
class CatalogRow:
    line: int
    character_stable_id: str
    character_name: str
    version_stable_id: str
    version_name: str
    release_date_global: date | None
    strategy: str
    distances: tuple[str, ...]
    surfaces: tuple[str, ...]

    @property
    def aptitudes(self) -> dict[str, tuple[str, ...]]:
        return {
            "strategy": (self.strategy,),
            "distance": self.distances,
            "surface": self.surfaces,
        }

    def payload(self) -> dict:
        return {
            "stable_id": self.version_stable_id,
            "display_name": self.version_name,
            "release_date_global": (
                self.release_date_global.isoformat() if self.release_date_global else None
            ),
            "aptitudes": {
                "strategy": [self.strategy],
                "distance": list(self.distances),
                "surface": list(self.surfaces),
            },
        }


@dataclass
class CatalogCharacter:
    stable_id: str
    display_name: str
    versions: list[CatalogRow] = field(default_factory=list)

    @property
    def has_global_release(self) -> bool:
        return any(row.release_date_global is not None for row in self.versions)

    def payload(self) -> dict:
        return {
            "character_stable_id": self.stable_id,
            "character_name": self.display_name,
            "versions": [row.payload() for row in self.versions],
        }


@dataclass
class CatalogParseReport:
    total_rows: int = 0
    rows: list[CatalogRow] = field(default_factory=list)
    characters: dict[str, CatalogCharacter] = field(default_factory=dict)
    errors: list[ImportIssue] = field(default_factory=list)
    ignored_lines: list[int] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def ignored_characters(self) -> list[CatalogCharacter]:
        return [
            character for character in self.characters.values() if not character.has_global_release
        ]

    def error_dicts(self) -> list[dict]:
        return [
            {"line": issue.line, "field": issue.field, "message": issue.message}
            for issue in self.errors
        ]


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    if not DATE_RE.match(value):
        raise ValueError("Data inválida; use o formato AAAA-MM-DD.")
    return date.fromisoformat(value)


def _parse_list(value: str, allowed: tuple[str, ...], label: str) -> tuple[str, ...]:
    values = tuple(part.strip() for part in value.split(";") if part.strip())
    if not values:
        raise ValueError(f"Informe ao menos um valor em {label}.")
    invalid = [item for item in values if item not in allowed]
    if invalid:
        raise ValueError(
            f"Valor inválido em {label}: {', '.join(invalid)} (use {', '.join(allowed)})."
        )
    return values


def _read_text(file_obj) -> str:
    if hasattr(file_obj, "read"):
        data = file_obj.read()
    else:
        with open(file_obj, "rb") as handle:
            data = handle.read()
    if isinstance(data, str):
        return data
    if len(data) > MAX_FILE_SIZE:
        raise ValueError("Arquivo excede o limite de 5 MB.")
    return data.decode("utf-8-sig")


def parse_catalog_csv(file_obj) -> CatalogParseReport:
    """Valida o catálogo inteiro sem gravar nada."""
    report = CatalogParseReport()

    try:
        text = _read_text(file_obj)
    except UnicodeDecodeError:
        report.errors.append(ImportIssue(None, "", "Arquivo deve estar codificado em UTF-8."))
        return report
    except ValueError as exc:
        report.errors.append(ImportIssue(None, "", str(exc)))
        return report

    if not text.strip():
        report.errors.append(ImportIssue(None, "", "Arquivo vazio."))
        return report

    try:
        reader = csv.DictReader(io.StringIO(text), strict=True)
        fieldnames = [name.strip() for name in (reader.fieldnames or [])]
        reader.fieldnames = fieldnames
        missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
        if missing:
            report.errors.append(
                ImportIssue(
                    None,
                    "",
                    f"Colunas obrigatórias ausentes: {', '.join(missing)}.",
                )
            )
            return report

        rows = list(reader)
    except csv.Error as exc:
        report.errors.append(ImportIssue(None, "", f"CSV inválido: {exc}."))
        return report

    seen_versions: dict[str, int] = {}
    character_names: dict[str, str] = {}

    for index, raw in enumerate(rows, start=2):
        if not any((value or "").strip() for value in raw.values() if isinstance(value, str)):
            continue

        report.total_rows += 1
        line = index
        values = {key: (raw.get(key) or "").strip() for key in REQUIRED_COLUMNS}

        error_count = len(report.errors)

        character_stable_id = values["character_stable_id"]
        if not character_stable_id:
            report.errors.append(
                ImportIssue(line, "character_stable_id", "Identificador da personagem vazio.")
            )
        elif not SLUG_RE.match(character_stable_id):
            report.errors.append(
                ImportIssue(
                    line,
                    "character_stable_id",
                    f"Slug inválido '{character_stable_id}' (use [a-z0-9-]).",
                )
            )

        character_name = values["character_name"]
        if not character_name:
            report.errors.append(ImportIssue(line, "character_name", "Nome da personagem vazio."))
        elif character_stable_id:
            previous = character_names.get(character_stable_id)
            if previous is not None and previous != character_name:
                report.errors.append(
                    ImportIssue(
                        line,
                        "character_name",
                        f"Nome divergente para '{character_stable_id}' (esperado '{previous}').",
                    )
                )
            else:
                character_names[character_stable_id] = character_name

        version_stable_id = values["version_stable_id"]
        if not version_stable_id:
            report.errors.append(
                ImportIssue(line, "version_stable_id", "Identificador da versão vazio.")
            )
        elif not SLUG_RE.match(version_stable_id):
            report.errors.append(
                ImportIssue(
                    line,
                    "version_stable_id",
                    f"Slug inválido '{version_stable_id}' (use [a-z0-9-]).",
                )
            )
        elif version_stable_id in seen_versions:
            report.errors.append(
                ImportIssue(
                    line,
                    "version_stable_id",
                    f"version_stable_id duplicado '{version_stable_id}' "
                    f"(já usado na linha {seen_versions[version_stable_id]}).",
                )
            )
        else:
            seen_versions[version_stable_id] = line

        version_name = values["version_name"]
        if not version_name:
            report.errors.append(ImportIssue(line, "version_name", "Nome da versão vazio."))

        try:
            release_date = _parse_date(values["release_date_global"])
        except ValueError as exc:
            report.errors.append(ImportIssue(line, "release_date_global", str(exc)))
            release_date = None

        strategy = values["strategy"]
        if strategy not in STRATEGIES:
            report.errors.append(
                ImportIssue(
                    line,
                    "strategy",
                    f"Estratégia inválida '{strategy}' (use {', '.join(STRATEGIES)}).",
                )
            )

        try:
            distances = _parse_list(values["distances"], DISTANCES, "distances")
        except ValueError as exc:
            report.errors.append(ImportIssue(line, "distances", str(exc)))
            distances = ()

        try:
            surfaces = _parse_list(values["surfaces"], SURFACES, "surfaces")
        except ValueError as exc:
            report.errors.append(ImportIssue(line, "surfaces", str(exc)))
            surfaces = ()

        if len(report.errors) != error_count:
            continue

        row = CatalogRow(
            line=line,
            character_stable_id=character_stable_id,
            character_name=character_name,
            version_stable_id=version_stable_id,
            version_name=version_name,
            release_date_global=release_date,
            strategy=strategy,
            distances=distances,
            surfaces=surfaces,
        )
        report.rows.append(row)
        character = report.characters.setdefault(
            character_stable_id,
            CatalogCharacter(stable_id=character_stable_id, display_name=character_name),
        )
        character.versions.append(row)

    if report.total_rows == 0:
        report.errors.append(ImportIssue(None, "", "Arquivo não contém linhas de catálogo."))

    if not report.has_errors:
        for character in report.ignored_characters:
            report.ignored_lines.extend(row.line for row in character.versions)

    return report


def parse_catalog_file(path: str) -> CatalogParseReport:
    with open(path, "rb") as handle:
        return parse_catalog_csv(handle)
