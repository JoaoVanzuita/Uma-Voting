#!/usr/bin/env python3
"""Baixa o elenco Global oficial e gera os manifestos locais.

Fonte principal: portal oficial Global (``umamusume.com``), cujo CMS expõe o
elenco e os ícones oficiais em PNG 400x400 com transparência.

Complemento: GameTora, usado apenas para datas de lançamento Global e
aptidões (estratégia/distância/superfície), que não existem na API oficial.

Uso::

    uv run python scripts/fetch_global_assets.py
    uv run python scripts/fetch_global_assets.py --skip-download
    uv run python scripts/fetch_global_assets.py --output-dir var/import/global

O script não altera o banco. Antes da primeira importação, registre a fonte
externa uma vez::

    python manage.py shell -c "from apps.catalog.models import CatalogSource; \\
        CatalogSource.objects.update_or_create(name='umamusume-global', defaults={ \\
        'kind': 'api', 'base_url': 'https://umamusume.com/characters/', \\
        'license_note': 'Imagens © Cygames, Inc. Uso interno.', 'enabled': True})"

Depois use os comandos já existentes::

    python manage.py import_catalog --file var/import/global/catalog.csv \
        --source curadoria-local --apply
    python manage.py import_images --manifest var/import/global/images.csv \
        --source-dir var/import/global/source --apply

As personagens ainda não lançadas no Global usam a data estimada do banner EN
do GameTora; o catálogo as mantém com data futura e a votação as filtra pela
data de corte.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

OFFICIAL_LIST_URL = "https://en-portal.g.kuroco.app/rcms-api/4/characters"
OFFICIAL_DETAIL_URL = "https://en-portal.g.kuroco.app/rcms-api/4/characters/{slug}"
OFFICIAL_PAGE_URL = "https://umamusume.com/characters/{slug}/"
GAMETORA_CHARACTERS_URL = "https://gametora.com/umamusume/characters"
GAMETORA_CARDS_FALLBACK = "https://gametora.com/data/umamusume/character-cards.0e9f93ec.json"
USER_AGENT = "uma-voting-local/1.0 (importação de catálogo; uso interno)"
SOURCE_NAME = "umamusume-global"
LICENSE_NOTE = "© Cygames, Inc. Uso interno; revisar autorização antes de publicar."
LOCAL_SOURCE_URL = "https://umamusume.com/characters/"

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

CATALOG_COLUMNS = (
    "character_stable_id",
    "character_name",
    "version_stable_id",
    "version_name",
    "release_date_global",
    "strategy",
    "distances",
    "surfaces",
)
IMAGE_COLUMNS = (
    "character_stable_id",
    "file",
    "source",
    "source_url",
    "license_note",
    "is_current",
)


@dataclass(frozen=True)
class GameToraCard:
    card_id: int
    char_id: int
    name_en: str
    url_name: str
    release_en: str | None
    aptitude: tuple[str, ...]


@dataclass
class CharacterAsset:
    official_slug: str
    stable_id: str
    name: str
    icon_url: str
    source_url: str
    release_date: date | None
    release_estimated: bool
    strategy: str
    distances: tuple[str, ...]
    surfaces: tuple[str, ...]
    visual_labels: tuple[str, ...]


class FetchError(RuntimeError):
    """Erro de rede ou de formato ao buscar uma fonte externa."""


def _request(url: str):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    return urllib.request.urlopen(request, timeout=30)


def fetch_bytes(url: str, *, retries: int = 3) -> bytes:
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with _request(url) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * attempt)
    raise FetchError(f"Falha ao baixar {url}: {last_error}") from last_error


def fetch_text(url: str, *, retries: int = 3) -> str:
    return fetch_bytes(url, retries=retries).decode("utf-8", errors="replace")


def fetch_json(url: str, *, retries: int = 3):
    return json.loads(fetch_bytes(url, retries=retries))


def map_concurrent(function, items, *, workers: int):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(function, items))


def normalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", value).casefold())


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = value.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-")


def discover_gametora_cards_url() -> str:
    """Descobre o JSON de cards do GameTora (o nome tem hash de conteúdo)."""
    html = fetch_text(GAMETORA_CHARACTERS_URL)
    chunks = sorted(set(re.findall(r"/_next/static/chunks/[^\"']+\.js", html)))
    for chunk in chunks:
        try:
            script = fetch_text(f"https://gametora.com{chunk}")
        except FetchError:
            continue
        match = re.search(r"/data/umamusume/character-cards\.[a-f0-9]+\.json", script)
        if match:
            return f"https://gametora.com{match.group(0)}"
    return GAMETORA_CARDS_FALLBACK


def discover_gametora_build_id() -> str:
    html = fetch_text(GAMETORA_CHARACTERS_URL)
    match = re.search(r'"buildId":"([^"]+)"', html)
    if not match:
        raise FetchError("Não foi possível descobrir o buildId do GameTora.")
    return match.group(1)


def fetch_gametora_cards(url: str) -> list[GameToraCard]:
    payload = fetch_json(url)
    cards: list[GameToraCard] = []
    for raw in payload:
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
            raise FetchError(f"Card inválido no GameTora: {raw!r}") from exc
    return cards


def fetch_gametora_release(
    build_id: str,
    url_name: str,
    *,
    cache: dict[str, tuple[date | None, bool]],
) -> tuple[date | None, bool]:
    """Data Global estimada a partir dos banners EN do GameTora."""
    if url_name in cache:
        return cache[url_name]

    url = f"https://gametora.com/_next/data/{build_id}/umamusume/characters/{url_name}.json"
    try:
        payload = fetch_json(url)
    except FetchError, json.JSONDecodeError:
        cache[url_name] = (None, False)
        return cache[url_name]

    banners = payload.get("pageProps", {}).get("sourceData", {}).get("banners", [])
    english = [item for item in banners if item.get("server") == "en"]
    if not english:
        cache[url_name] = (None, False)
        return cache[url_name]

    earliest = min(english, key=lambda item: int(item["start"]))
    released = datetime.fromtimestamp(int(earliest["start"]), UTC).date()
    cache[url_name] = (released, bool(earliest.get("is_estimated")))
    return cache[url_name]


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


def best_strategy(grades: dict[str, str]) -> str:
    present = [(grades[key], key) for key in STRATEGY_KEYS if grades.get(key)]
    if not present:
        raise FetchError("Personagem sem aptidão de estratégia.")
    best_grade = min(present, key=lambda item: GRADE_ORDER.get(item[0], 99))[0]
    return next(key for grade, key in present if grade == best_grade)


def build_assets(
    official: list[dict],
    cards: list[GameToraCard],
    build_id: str,
    *,
    workers: int,
) -> tuple[list[CharacterAsset], list[str]]:
    cards_by_name: dict[str, list[GameToraCard]] = {}
    for card in cards:
        cards_by_name.setdefault(normalize_name(card.name_en), []).append(card)
    for group in cards_by_name.values():
        group.sort(key=lambda card: card.card_id)

    release_cache: dict[str, tuple[date | None, bool]] = {}
    warnings: list[str] = []
    assets: list[CharacterAsset] = []

    def official_detail(character: dict) -> tuple[dict, dict]:
        slug = character["slug"]
        try:
            payload = fetch_json(OFFICIAL_DETAIL_URL.format(slug=slug))
            return character, payload.get("details", {})
        except (FetchError, json.JSONDecodeError) as exc:
            raise FetchError(f"Detalhe oficial de {slug}: {exc}") from exc

    details = map_concurrent(official_detail, official, workers=workers)

    for character, detail in details:
        name = str(character.get("subject") or "").strip()
        official_slug = str(character.get("slug") or "").strip()
        stable_id = slugify(name)
        if not name or not official_slug or not stable_id:
            warnings.append(f"Personagem oficial inválida: {character!r}")
            continue

        matching = cards_by_name.get(normalize_name(name), [])
        if not matching:
            warnings.append(f"Sem metadados do GameTora para {name!r}.")
            continue

        original = matching[0]
        if len(original.aptitude) != len(APTITUDE_KEYS):
            warnings.append(f"Aptidões inesperadas para {name!r}: {original.aptitude!r}.")
            continue
        grades = dict(zip(APTITUDE_KEYS, original.aptitude, strict=True))

        release_dates = [
            date.fromisoformat(card.release_en) for card in matching if card.release_en
        ]
        estimated = False
        if release_dates:
            release_date = min(release_dates)
        else:
            found: list[tuple[date, bool]] = []
            for card in matching:
                candidate = fetch_gametora_release(
                    build_id,
                    card.url_name,
                    cache=release_cache,
                )
                if candidate[0] is not None:
                    found.append(candidate)  # type: ignore[arg-type]
            if found:
                found.sort(key=lambda item: item[0])
                release_date, estimated = found[0]
            else:
                release_date = None
                warnings.append(f"Sem data Global conhecida para {name!r}.")

        icon_url = str((detail.get("download") or {}).get("icon") or "").strip()
        if not icon_url:
            icon_url = (
                "https://en-portal.g.kuroco-img.app/files/user/character/"
                f"{official_slug}/{official_slug}_icon.png"
            )

        visual_labels = tuple(
            str((visual.get("name") or {}).get("label") or "")
            for visual in (detail.get("visual") or [])
            if visual.get("name")
        )

        assets.append(
            CharacterAsset(
                official_slug=official_slug,
                stable_id=stable_id,
                name=name,
                icon_url=icon_url,
                source_url=OFFICIAL_PAGE_URL.format(slug=official_slug),
                release_date=release_date,
                release_estimated=estimated,
                strategy=best_strategy(grades),
                distances=best_values(grades, DISTANCE_KEYS),
                surfaces=best_values(grades, SURFACE_KEYS),
                visual_labels=visual_labels,
            )
        )

    return assets, warnings


def download_icon(asset: CharacterAsset, source_dir: Path, *, force: bool) -> str | None:
    destination = source_dir / f"{asset.stable_id}.png"
    if destination.exists() and destination.stat().st_size > 0 and not force:
        return None

    try:
        data = fetch_bytes(asset.icon_url)
    except FetchError as exc:
        return f"{asset.name}: {exc}"
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return f"{asset.name}: resposta não é PNG."

    source_dir.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return None


def write_catalog(path: Path, assets: list[CharacterAsset]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CATALOG_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for asset in assets:
            writer.writerow(
                {
                    "character_stable_id": asset.stable_id,
                    "character_name": asset.name,
                    "version_stable_id": f"{asset.stable_id}-original",
                    "version_name": f"{asset.name} (Original)",
                    "release_date_global": (
                        asset.release_date.isoformat() if asset.release_date else ""
                    ),
                    "strategy": asset.strategy,
                    "distances": ";".join(asset.distances),
                    "surfaces": ";".join(asset.surfaces),
                }
            )


def write_images(path: Path, assets: list[CharacterAsset]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=IMAGE_COLUMNS, lineterminator="\n")
        writer.writeheader()
        for asset in assets:
            writer.writerow(
                {
                    "character_stable_id": asset.stable_id,
                    "file": f"{asset.stable_id}.png",
                    "source": SOURCE_NAME,
                    "source_url": asset.source_url,
                    "license_note": LICENSE_NOTE,
                    "is_current": "true",
                }
            )


def write_metadata(path: Path, assets: list[CharacterAsset]) -> None:
    payload = [
        {
            "official_slug": asset.official_slug,
            "stable_id": asset.stable_id,
            "name": asset.name,
            "release_date_global": (asset.release_date.isoformat() if asset.release_date else None),
            "release_estimated": asset.release_estimated,
            "strategy": asset.strategy,
            "distances": list(asset.distances),
            "surfaces": list(asset.surfaces),
            "visual_labels": list(asset.visual_labels),
            "icon_url": asset.icon_url,
            "source_url": asset.source_url,
            "license_note": LICENSE_NOTE,
        }
        for asset in assets
    ]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("var/import/global"),
        help="Diretório de saída (padrão: var/import/global).",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Gera apenas os CSV/JSON, sem baixar ícones.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Baixa novamente ícones já existentes.",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=6,
        help="Requisições concorrentes (padrão: 6).",
    )
    parser.add_argument(
        "--gametora-cards",
        default=None,
        help="URL alternativa do JSON character-cards do GameTora.",
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    return parser.parse_args()


def main() -> int:
    options = parse_args()
    output_dir: Path = options.output_dir
    source_dir = output_dir / "source"
    output_dir.mkdir(parents=True, exist_ok=True)

    official = fetch_json(OFFICIAL_LIST_URL).get("umamusume") or []
    if not official:
        raise SystemExit("A API oficial não retornou personagens.")

    cards_url = options.gametora_cards or discover_gametora_cards_url()
    cards = fetch_gametora_cards(cards_url)
    build_id = discover_gametora_build_id()

    assets, warnings = build_assets(
        official,
        cards,
        build_id,
        workers=max(1, options.workers),
    )
    assets.sort(key=lambda asset: asset.name.casefold())

    release_today = date.today()
    released = sum(
        1 for asset in assets if asset.release_date and asset.release_date <= release_today
    )
    upcoming = sum(
        1 for asset in assets if asset.release_date and asset.release_date > release_today
    )
    unknown = sum(1 for asset in assets if asset.release_date is None)

    download_errors: list[str] = []
    if not options.skip_download:
        download_errors = [
            error
            for error in map_concurrent(
                lambda asset: download_icon(asset, source_dir, force=options.force),
                assets,
                workers=max(1, options.workers),
            )
            if error
        ]

    write_catalog(output_dir / "catalog.csv", assets)
    write_images(output_dir / "images.csv", assets)
    write_metadata(output_dir / "global-metadata.json", assets)

    summary = {
        "characters": len(assets),
        "released_global": released,
        "upcoming_global": upcoming,
        "without_release_date": unknown,
        "icons_downloaded": 0 if options.skip_download else len(assets) - len(download_errors),
        "output_dir": str(output_dir),
        "catalog": str(output_dir / "catalog.csv"),
        "images": str(output_dir / "images.csv"),
        "metadata": str(output_dir / "global-metadata.json"),
        "warnings": warnings,
        "errors": download_errors,
    }

    if options.as_json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"{len(assets)} personagem(ns); {released} lançada(s) no Global; "
            f"{upcoming} futura(s); {unknown} sem data."
        )
        if not options.skip_download:
            print(f"{summary['icons_downloaded']} ícone(s) baixado(s) em {source_dir}.")
        print(f"Catálogo: {summary['catalog']}")
        print(f"Manifesto: {summary['images']}")
        print(f"Metadados: {summary['metadata']}")
        for warning in warnings:
            print(f"Aviso: {warning}", file=sys.stderr)
        for error in download_errors:
            print(f"Erro: {error}", file=sys.stderr)

    return 1 if download_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
