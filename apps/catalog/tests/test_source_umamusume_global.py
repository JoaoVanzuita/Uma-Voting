"""Testes do conector Umamusume Global (portal oficial + GameTora)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from apps.catalog.services.sources.base import (
    SourceDataError,
    SourceHTTPError,
    SourceUnavailableError,
)
from apps.catalog.services.sources.umamusume_global import (
    GAMETORA_CARDS_FALLBACK,
    GAMETORA_CHARACTERS_URL,
    GAMETORA_RELEASE_URL,
    OFFICIAL_DETAIL_URL,
    OFFICIAL_ICON_FALLBACK,
    OFFICIAL_LIST_URL,
    UmamusumeGlobalAdapter,
    best_strategy,
    best_values,
    normalize_name,
    slugify,
)
from tests.factories import CatalogSourceFactory

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).parent / "fixtures" / "sources"
CARDS_URL = "https://gametora.com/data/umamusume/character-cards.abc123.json"
CHUNK_URL = "https://gametora.com/_next/static/chunks/main-abc.js"
BUILD_ID = "test-build"
CHUNK_SCRIPT = f'const url = "{CARDS_URL.replace("https://gametora.com", "")}";'


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeClient:
    def __init__(self, *, json_responses=None, text_responses=None):
        self.json_responses = dict(json_responses or {})
        self.text_responses = dict(text_responses or {})
        self.calls: list[str] = []

    def get_json(self, url, *, max_bytes=None):
        self.calls.append(url)
        value = self.json_responses.get(url)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise SourceHTTPError("não encontrado", status=404, url=url)
        return value

    def get_text(self, url, *, max_bytes=None):
        self.calls.append(url)
        value = self.text_responses.get(url)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise SourceHTTPError("não encontrado", status=404, url=url)
        return value


def make_client(
    *,
    official=None,
    detail=None,
    cards=None,
    detail_errors: dict[str, Exception] | None = None,
    html: str | None = None,
) -> FakeClient:
    official = official if official is not None else load_fixture("official_characters.json")
    detail = detail if detail is not None else load_fixture("official_character_detail.json")
    cards = cards if cards is not None else load_fixture("gametora_cards.json")

    json_responses = {OFFICIAL_LIST_URL: official, CARDS_URL: cards}
    for entry in official.get("umamusume", []):
        slug = entry["slug"]
        error = (detail_errors or {}).get(slug)
        json_responses[OFFICIAL_DETAIL_URL.format(slug=slug)] = error or detail
    json_responses[GAMETORA_RELEASE_URL.format(build_id=BUILD_ID, url_name="symboli-rudolf")] = (
        load_fixture("gametora_release.json")
    )

    text_responses = {
        GAMETORA_CHARACTERS_URL: html
        if html is not None
        else f'<html><script>"buildId":"{BUILD_ID}"</script>'
        f'<script src="/_next/static/chunks/main-abc.js"></script></html>',
        CHUNK_URL: CHUNK_SCRIPT,
    }
    return FakeClient(json_responses=json_responses, text_responses=text_responses)


@pytest.fixture
def source():
    return CatalogSourceFactory(
        name="umamusume-global",
        adapter="umamusume-global",
        license_note="Uso interno.",
    )


@pytest.fixture(autouse=True)
def single_worker(settings):
    settings.EXTERNAL_IMPORT_CONCURRENCY = 1


def build_adapter(source, client) -> UmamusumeGlobalAdapter:
    return UmamusumeGlobalAdapter(source, client=client)


# ---------------------------------------------------------------------------
# Utilidades de normalização
# ---------------------------------------------------------------------------
def test_normaliza_nome_e_slug():
    assert normalize_name("Special Week") == "specialweek"
    assert normalize_name("Mejiro Dober") == "mejirodober"
    assert slugify("Special Week") == "special-week"
    assert slugify("Mejiro & McQueen") == "mejiro-and-mcqueen"


def test_melhor_estrategia_e_valores_por_grau():
    grades = {"front": "B", "pace": "A", "late": "C", "end": "G"}
    assert best_strategy(grades) == "pace"
    assert best_strategy({}) is None
    distances = {"sprint": "C", "mile": "A", "medium": "S", "long": "A"}
    assert best_values(grades={}, keys=()) == ()
    assert set(best_values(distances, ("sprint", "mile", "medium", "long"))) == {
        "mile",
        "medium",
        "long",
    }
    fallback = {"sprint": "B", "mile": "C", "medium": "B", "long": "D"}
    assert set(best_values(fallback, ("sprint", "mile", "medium", "long"))) == {
        "sprint",
        "medium",
    }


# ---------------------------------------------------------------------------
# Parsing do catálogo (T028)
# ---------------------------------------------------------------------------
def test_parseia_lista_detalhe_e_cards(source):
    adapter = build_adapter(source, make_client())

    report = adapter.fetch_catalog()

    assert not report.has_errors
    assert report.total_rows == 4
    assert set(report.characters) == {
        "special-week",
        "silence-suzuka",
        "tokai-teio",
        "symboli-rudolf",
    }

    special = report.characters["special-week"]
    assert special.display_name == "Special Week"
    row = special.versions[0]
    assert row.version_stable_id == "special-week-original"
    assert row.version_name == "Special Week (Original)"
    assert row.release_date_global == date(2025, 6, 26)
    assert row.strategy == "front"
    assert set(row.distances) == {"mile", "medium", "long"}
    assert row.surfaces == ("turf",)


def test_detalhe_404_vira_aviso_e_nao_aborta(source):
    adapter = build_adapter(
        source,
        make_client(
            detail_errors={
                "silence-suzuka": SourceHTTPError("sumiu", status=404, url="x"),
            }
        ),
    )

    report = adapter.fetch_catalog()

    assert not report.has_errors
    assert "silence-suzuka" not in report.characters
    assert any("404" in warning for warning in report.warnings)


def test_lista_oficial_vazia_e_erro(source):
    adapter = build_adapter(source, make_client(official={"umamusume": []}))

    with pytest.raises(SourceDataError, match="não retornou personagens"):
        adapter.fetch_catalog()


def test_todos_os_detalhes_falham_e_erro(source):
    adapter = build_adapter(
        source,
        make_client(
            detail_errors={
                "special-week": SourceHTTPError("erro", status=503, url="x"),
                "silence-suzuka": SourceHTTPError("erro", status=503, url="x"),
                "tokai-teio": SourceHTTPError("erro", status=503, url="x"),
                "symboli-rudolf": SourceHTTPError("erro", status=503, url="x"),
            }
        ),
    )

    with pytest.raises(SourceUnavailableError):
        adapter.fetch_catalog()


def test_identificador_duplicado_e_erro(source):
    official = {
        "umamusume": [
            {"slug": "special-week", "subject": "Special Week"},
            {"slug": "special-week-2", "subject": "Special Week"},
        ]
    }
    adapter = build_adapter(source, make_client(official=official))

    with pytest.raises(SourceDataError, match="mesmo identificador"):
        adapter.fetch_catalog()


def test_sem_card_no_gametora_vira_aviso(source):
    cards = [
        card for card in load_fixture("gametora_cards.json") if card["name_en"] != "Tokai Teio"
    ]
    adapter = build_adapter(source, make_client(cards=cards))

    report = adapter.fetch_catalog()

    assert "tokai-teio" not in report.characters
    assert any("Tokai Teio" in warning for warning in report.warnings)


def test_aptidoes_incompletas_viram_aviso(source):
    cards = load_fixture("gametora_cards.json")
    for card in cards:
        if card["name_en"] == "Special Week":
            card["aptitude"] = ["A", "G"]
    adapter = build_adapter(source, make_client(cards=cards))

    report = adapter.fetch_catalog()

    assert "special-week" not in report.characters
    assert any("Aptidões inesperadas" in warning for warning in report.warnings)


# ---------------------------------------------------------------------------
# GameTora: descoberta, build ID e datas estimadas (T029)
# ---------------------------------------------------------------------------
def test_descobre_cards_e_build_id_e_estima_data(source):
    client = make_client()
    adapter = build_adapter(source, client)

    report = adapter.fetch_catalog()

    assert CARDS_URL in client.calls
    assert CHUNK_URL in client.calls
    assert GAMETORA_RELEASE_URL.format(build_id=BUILD_ID, url_name="symboli-rudolf") in client.calls
    rudolf = report.characters["symboli-rudolf"].versions[0]
    assert rudolf.release_date_global == date(2025, 8, 14)


def test_usa_fallback_quando_descoberta_falha(source, settings):
    settings.EXTERNAL_IMPORT_CONCURRENCY = 1
    official = load_fixture("official_characters.json")
    detail = load_fixture("official_character_detail.json")
    cards = load_fixture("gametora_cards.json")
    json_responses = {
        OFFICIAL_LIST_URL: official,
        CARDS_URL: cards,
    }
    for entry in official["umamusume"]:
        json_responses[OFFICIAL_DETAIL_URL.format(slug=entry["slug"])] = detail
    client = FakeClient(
        json_responses=json_responses,
        text_responses={
            GAMETORA_CHARACTERS_URL: f'<html>"buildId":"{BUILD_ID}"</html>',
        },
    )
    adapter = build_adapter(source, client)

    # Sem chunk acessível, o conector usa a URL fixa documentada.
    with pytest.raises(SourceUnavailableError):
        adapter.fetch_catalog()
    assert GAMETORA_CARDS_FALLBACK in client.calls


def test_sem_data_conhecida_vira_aviso_e_personagem_ignorada(source):
    cards = load_fixture("gametora_cards.json")
    for card in cards:
        if card["name_en"] == "Symboli Rudolf":
            card["release_en"] = None
    official = load_fixture("official_characters.json")
    detail = load_fixture("official_character_detail.json")
    json_responses = {OFFICIAL_LIST_URL: official, CARDS_URL: cards}
    for entry in official["umamusume"]:
        json_responses[OFFICIAL_DETAIL_URL.format(slug=entry["slug"])] = detail
    client = FakeClient(
        json_responses=json_responses,
        text_responses={
            GAMETORA_CHARACTERS_URL: f'<html>"buildId":"{BUILD_ID}"'
            f'<script src="/_next/static/chunks/main-abc.js"></script></html>',
            CHUNK_URL: CHUNK_SCRIPT,
        },
    )
    # Build ID e cards são descobertos; o release.json não está disponível.
    adapter = build_adapter(source, client)

    report = adapter.fetch_catalog()

    assert "symboli-rudolf" in report.characters
    assert report.characters["symboli-rudolf"].versions[0].release_date_global is None
    assert report.ignored_characters
    assert any("Sem data Global" in warning for warning in report.warnings)


def test_gametora_indisponivel_e_erro(source):
    client = make_client()
    client.json_responses[CARDS_URL] = SourceHTTPError("fora", status=503, url="x")
    adapter = build_adapter(source, client)

    with pytest.raises(SourceUnavailableError):
        adapter.fetch_catalog()


def test_check_usa_lista_oficial(source):
    adapter = build_adapter(source, make_client())
    result = adapter.check()
    assert result.ok is True
    assert "4 personagem" in result.message

    failing = make_client()
    failing.json_responses[OFFICIAL_LIST_URL] = SourceHTTPError("fora", status=503, url="x")
    result = build_adapter(source, failing).check()
    assert result.ok is False
    assert "fora" in result.message


def test_icon_url_usa_detalhe_e_fallback(source):
    adapter = build_adapter(source, make_client())
    adapter.fetch_catalog()

    assert adapter.icon_url("Special Week").endswith("special-week_icon.png")
    assert adapter.icon_url("Personagem Desconhecida") == OFFICIAL_ICON_FALLBACK.format(
        slug="personagem-desconhecida"
    )
