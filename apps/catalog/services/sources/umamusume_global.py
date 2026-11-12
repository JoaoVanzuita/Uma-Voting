"""Conector da fonte Global de Umamusume.

Combina o portal oficial (elenco, detalhes e ícones) com o GameTora (datas de
lançamento Global e aptidões). Nenhuma URL é recebida do usuário: hosts, rotas e
fallbacks vivem neste módulo e no registry.
"""

from __future__ import annotations

import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime

from django.conf import settings
from django.utils import timezone

from apps.catalog.models import CatalogSource
from apps.catalog.services.importers import (
    CatalogCharacter,
    CatalogParseReport,
    CatalogRow,
)
from apps.catalog.services.sources.base import (
    SourceCheckResult,
    SourceDataError,
    SourceError,
    SourceHTTPError,
    SourceUnavailableError,
)
from apps.catalog.services.sources.http import HttpClient

OFFICIAL_LIST_URL = "https://en-portal.g.kuroco.app/rcms-api/4/characters"
OFFICIAL_DETAIL_URL = "https://en-portal.g.kuroco.app/rcms-api/4/characters/{slug}"
OFFICIAL_PAGE_URL = "https://umamusume.com/characters/{slug}/"
OFFICIAL_ICON_FALLBACK = (
    "https://en-portal.g.kuroco-img.app/files/user/character/{slug}/{slug}_icon.png"
)
GAMETORA_CHARACTERS_URL = "https://gametora.com/umamusume/characters"
GAMETORA_CARDS_FALLBACK = "https://gametora.com/data/umamusume/character-cards.0e9f93ec.json"
GAMETORA_RELEASE_URL = (
    "https://gametora.com/_next/data/{build_id}/umamusume/characters/{url_name}.json"
)
USER_AGENT = "uma-voting-import/1.0 (importação de catálogo; uso interno)"

APTITUDE_KEYS = (
    "turf",
    "dirt",
    "sprint",
    "mile",
    "medium",
    "long",
    "front",
    "pace",
    "late",
    "end",
)
GRADE_ORDER = {grade: index for index, grade in enumerate("SABCDEFG")}
STRATEGY_KEYS = ("front", "pace", "late", "end")
DISTANCE_KEYS = ("sprint", "mile", "medium", "long")
SURFACE_KEYS = ("turf", "dirt")

_CARDS_RE = re.compile(r"/data/umamusume/character-cards\.[a-f0-9]+\.json")
_CHUNK_RE = re.compile(r"/_next/static/chunks/[^\"']+\.js")
_BUILD_ID_RE = re.compile(r'"buildId":"([^"]+)"')


@dataclass(frozen=True)
class GameToraCard:
    card_id: int
    char_id: int
    name_en: str
    url_name: str
    release_en: str | None
    aptitude: tuple[str, ...]


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", value).casefold())


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def best_values(
    grades: dict[str, str],
    keys: tuple[str, ...],
    *,
    preferred: tuple[str, ...] = ("S", "A"),
) -> tuple[str, ...]:
    selected = [key for key in keys if grades.get(key) in preferred]
    if selected:
        return tuple(selected)

    present = [(grades[key], key) for key in keys if grades.get(key)]
    if not present:
        return ()
    best_grade = min(present, key=lambda item: GRADE_ORDER.get(item[0], 99))[0]
    return tuple(key for grade, key in present if grade == best_grade)


def best_strategy(grades: dict[str, str]) -> str | None:
    present = [(grades[key], key) for key in STRATEGY_KEYS if grades.get(key)]
    if not present:
        return None
    best_grade = min(present, key=lambda item: GRADE_ORDER.get(item[0], 99))[0]
    return next(key for grade, key in present if grade == best_grade)


class UmamusumeGlobalAdapter:
    key = "umamusume-global"
    display_name = "Umamusume Global (portal oficial + GameTora)"
    allowed_hosts = (
        "en-portal.g.kuroco.app",
        "en-portal.g.kuroco-img.app",
        "umamusume.com",
        "gametora.com",
    )

    def __init__(self, source: CatalogSource, *, client: HttpClient | None = None) -> None:
        self.source = source
        self.client = client or HttpClient(
            allowed_hosts=self.allowed_hosts,
            timeout=settings.EXTERNAL_IMPORT_HTTP_TIMEOUT,
            user_agent=USER_AGENT,
        )
        options = source.options or {}
        self._cards_url_override = str(options.get("gametora_cards_url") or "").strip()
        self._build_id_override = str(options.get("gametora_build_id") or "").strip()
        self._detail_cache: dict[str, dict] = {}
        self._release_cache: dict[str, tuple[date | None, bool]] = {}
        self._gametora_html: str | None = None

    # ------------------------------------------------------------------
    # Catálogo
    # ------------------------------------------------------------------
    def fetch_catalog(self) -> CatalogParseReport:
        report = CatalogParseReport()
        official = self._fetch_official_list()
        details = self._fetch_official_details(official, report)
        cards = self._fetch_gametora_cards()
        cards_by_name = self._group_cards(cards)

        build_id: str | None = None
        seen_stable_ids: set[str] = set()

        for entry, detail in details:
            name = str(entry.get("subject") or "").strip()
            slug = str(entry.get("slug") or "").strip()
            stable_id = slugify(name)

            if not name or not slug or not stable_id:
                report.warnings.append(f"Personagem oficial inválida: {entry!r}")
                continue
            if stable_id in seen_stable_ids:
                raise SourceDataError(
                    f"Duas personagens normalizam para o mesmo identificador '{stable_id}'."
                )
            seen_stable_ids.add(stable_id)

            matching = cards_by_name.get(normalize_name(name), [])
            if not matching:
                report.warnings.append(f"Sem metadados do GameTora para {name!r}.")
                continue

            original = matching[0]
            if len(original.aptitude) != len(APTITUDE_KEYS):
                report.warnings.append(
                    f"Aptidões inesperadas para {name!r}: {original.aptitude!r}."
                )
                continue

            grades = dict(zip(APTITUDE_KEYS, original.aptitude, strict=True))
            strategy = best_strategy(grades)
            distances = best_values(grades, DISTANCE_KEYS)
            surfaces = best_values(grades, SURFACE_KEYS)
            if strategy is None or not distances or not surfaces:
                report.warnings.append(f"Aptidões incompletas para {name!r}.")
                continue

            release_dates = []
            for card in matching:
                if not card.release_en:
                    continue
                try:
                    release_dates.append(date.fromisoformat(card.release_en))
                except ValueError:
                    report.warnings.append(
                        f"Data inválida do GameTora para {name!r}: {card.release_en!r}."
                    )

            if not release_dates:
                if build_id is None:
                    build_id = self._discover_build_id()
                release_date = self._estimate_release(build_id, matching)
                if release_date is None:
                    report.warnings.append(f"Sem data Global conhecida para {name!r}.")
            else:
                release_date = min(release_dates)

            row = CatalogRow(
                line=len(report.rows) + 1,
                character_stable_id=stable_id,
                character_name=name,
                version_stable_id=f"{stable_id}-original",
                version_name=f"{name} (Original)",
                release_date_global=release_date,
                strategy=strategy,
                distances=distances,
                surfaces=surfaces,
            )
            report.rows.append(row)
            character = report.characters.setdefault(
                stable_id,
                CatalogCharacter(stable_id=stable_id, display_name=name),
            )
            character.versions.append(row)
            self._detail_cache.setdefault(slug, detail)

        report.total_rows = len(report.rows)
        report.ignored_lines = [
            row.line for character in report.ignored_characters for row in character.versions
        ]
        return report

    def check(self) -> SourceCheckResult:
        checked_at = timezone.now()
        try:
            official = self._fetch_official_list()
        except SourceError as exc:
            return SourceCheckResult(ok=False, message=str(exc), checked_at=checked_at)

        if not official:
            return SourceCheckResult(
                ok=False,
                message="A lista oficial não retornou personagens.",
                checked_at=checked_at,
            )
        return SourceCheckResult(
            ok=True,
            message=f"{len(official)} personagem(ns) na lista oficial.",
            checked_at=checked_at,
        )

    # ------------------------------------------------------------------
    # Portal oficial
    # ------------------------------------------------------------------
    def _fetch_official_list(self) -> list[dict]:
        payload = self.client.get_json(OFFICIAL_LIST_URL)
        if not isinstance(payload, dict):
            raise SourceDataError("Resposta da lista oficial não é um objeto JSON.")
        official = payload.get("umamusume") or []
        if not isinstance(official, list):
            raise SourceDataError("Campo 'umamusume' da lista oficial é inválido.")
        if not official:
            raise SourceDataError("A lista oficial não retornou personagens.")
        return [entry for entry in official if isinstance(entry, dict)]

    def _fetch_official_details(
        self,
        official: list[dict],
        report: CatalogParseReport,
    ) -> list[tuple[dict, dict]]:
        def load(entry: dict) -> tuple[dict, dict] | None:
            slug = str(entry.get("slug") or "").strip()
            try:
                payload = self.client.get_json(OFFICIAL_DETAIL_URL.format(slug=slug))
            except SourceHTTPError as exc:
                if exc.status == 404:
                    report.warnings.append(f"Detalhe oficial ausente para {slug!r} (HTTP 404).")
                return None
            except SourceError:
                return None
            if not isinstance(payload, dict):
                return None
            detail = payload.get("details") or {}
            if not isinstance(detail, dict):
                return None
            self._detail_cache[slug] = detail
            return entry, detail

        workers = max(1, settings.EXTERNAL_IMPORT_CONCURRENCY)
        if workers == 1 or len(official) == 1:
            results = [load(entry) for entry in official]
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(load, official))

        loaded = [item for item in results if item is not None]
        if not loaded and official:
            raise SourceUnavailableError(
                "Todos os detalhes oficiais falharam; a fonte está indisponível."
            )
        return loaded

    def icon_url(self, name: str) -> str:
        slug = slugify(name)
        detail = self._detail_cache.get(slug) or {}
        download = detail.get("download") or {}
        icon = str(download.get("icon") or "").strip()
        if icon:
            return icon
        return OFFICIAL_ICON_FALLBACK.format(slug=slug)

    # ------------------------------------------------------------------
    # GameTora
    # ------------------------------------------------------------------
    def _gametora_page(self) -> str:
        if self._gametora_html is None:
            self._gametora_html = self.client.get_text(GAMETORA_CHARACTERS_URL)
        return self._gametora_html

    def _discover_cards_url(self) -> str:
        if self._cards_url_override:
            return self._cards_url_override

        html = self._gametora_page()
        for chunk in sorted(set(_CHUNK_RE.findall(html))):
            try:
                script = self.client.get_text(f"https://gametora.com{chunk}")
            except SourceError:
                continue
            match = _CARDS_RE.search(script)
            if match:
                return f"https://gametora.com{match.group(0)}"
        return GAMETORA_CARDS_FALLBACK

    def _discover_build_id(self) -> str:
        if self._build_id_override:
            return self._build_id_override
        match = _BUILD_ID_RE.search(self._gametora_page())
        if not match:
            raise SourceDataError("Não foi possível descobrir o buildId do GameTora.")
        return match.group(1)

    def _fetch_gametora_cards(self) -> list[GameToraCard]:
        try:
            url = self._discover_cards_url()
        except SourceError as exc:
            raise SourceUnavailableError(f"GameTora indisponível: {exc}") from exc

        try:
            payload = self.client.get_json(url)
        except SourceError as exc:
            raise SourceUnavailableError(f"GameTora indisponível: {exc}") from exc

        if not isinstance(payload, list) or not payload:
            raise SourceDataError("O GameTora não retornou cards de personagens.")

        cards: list[GameToraCard] = []
        for raw in payload:
            if not isinstance(raw, dict):
                continue
            try:
                cards.append(
                    GameToraCard(
                        card_id=int(raw["card_id"]),
                        char_id=int(raw["char_id"]),
                        name_en=str(raw["name_en"]),
                        url_name=str(raw["url_name"]),
                        release_en=raw.get("release_en") or None,
                        aptitude=tuple(raw.get("aptitude") or ()),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise SourceDataError(f"Card inválido no GameTora: {raw!r}") from exc
        return cards

    @staticmethod
    def _group_cards(cards: list[GameToraCard]) -> dict[str, list[GameToraCard]]:
        grouped: dict[str, list[GameToraCard]] = {}
        for card in cards:
            grouped.setdefault(normalize_name(card.name_en), []).append(card)
        for group in grouped.values():
            group.sort(key=lambda card: card.card_id)
        return grouped

    def _estimate_release(
        self,
        build_id: str,
        cards: list[GameToraCard],
    ) -> date | None:
        found: list[date] = []
        for card in cards:
            candidate = self._fetch_release(build_id, card.url_name)
            if candidate is not None:
                found.append(candidate)
        return min(found) if found else None

    def _fetch_release(self, build_id: str, url_name: str) -> date | None:
        if url_name in self._release_cache:
            return self._release_cache[url_name][0]
        try:
            payload = self.client.get_json(
                GAMETORA_RELEASE_URL.format(build_id=build_id, url_name=url_name)
            )
        except SourceError:
            self._release_cache[url_name] = (None, False)
            return None

        banners = (
            (payload or {}).get("pageProps", {}).get("sourceData", {}).get("banners", [])
            if isinstance(payload, dict)
            else []
        )
        english = [item for item in banners if item.get("server") == "en"]
        if not english:
            self._release_cache[url_name] = (None, False)
            return None
        try:
            earliest = min(english, key=lambda item: int(item["start"]))
            released = datetime.fromtimestamp(int(earliest["start"]), UTC).date()
        except KeyError, TypeError, ValueError:
            self._release_cache[url_name] = (None, False)
            return None
        self._release_cache[url_name] = (released, True)
        return released

    # ------------------------------------------------------------------
    # Imagens (implementado na fase de imagens)
    # ------------------------------------------------------------------
    def iter_images(self, characters, *, only_missing: bool):
        raise NotImplementedError("A coleta de imagens é implementada na fase de imagens.")
        yield  # pragma: no cover
