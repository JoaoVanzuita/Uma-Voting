"""Contrato dos conectores de fontes externas."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from apps.catalog.models import Character
from apps.catalog.services.importers import CatalogParseReport


class SourceError(Exception):
    """Falha genérica de coleta em uma fonte externa."""


class SourceHTTPError(SourceError):
    """Falha HTTP: status, timeout, tamanho ou redirecionamento inválido."""

    def __init__(self, message: str, *, status: int | None = None, url: str = "") -> None:
        super().__init__(message)
        self.status = status
        self.url = url


class SourceDataError(SourceError):
    """Conteúdo da fonte com schema ou dados inesperados."""


class SourceUnavailableError(SourceError):
    """Fonte indisponível durante a verificação de disponibilidade."""


@dataclass(frozen=True)
class ImageCandidate:
    """Imagem coletada, ainda não validada nem gravada."""

    character_stable_id: str
    data: bytes
    source_url: str
    content_type: str = ""


@dataclass(frozen=True)
class ImageFetchError:
    """Falha isolada ao baixar uma imagem; não interrompe as demais."""

    character_stable_id: str
    source_url: str
    message: str


@dataclass(frozen=True)
class SourceCheckResult:
    """Resultado da verificação de disponibilidade da fonte."""

    ok: bool
    message: str
    checked_at: datetime


class ExternalSourceAdapter(Protocol):
    """Protocolo implementado por cada conector registrado em código."""

    key: str
    display_name: str
    allowed_hosts: tuple[str, ...]

    def fetch_catalog(self) -> CatalogParseReport: ...

    def iter_images(
        self,
        characters: Iterable[Character],
        *,
        only_missing: bool,
    ) -> Iterator[ImageCandidate | ImageFetchError]: ...

    def check(self) -> SourceCheckResult: ...
