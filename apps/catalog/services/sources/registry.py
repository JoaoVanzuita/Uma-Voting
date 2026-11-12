"""Registry estático dos conectores de fontes externas.

O registry é preenchido em tempo de importação do módulo, sem descoberta
dinâmica de pacotes. Adicionar uma fonte exige um módulo de conector, o
registro da chave em ``ADAPTERS`` e a criação/atualização de ``CatalogSource``.
"""

from __future__ import annotations

from django.db.models import QuerySet

from apps.catalog.models import CatalogSource
from apps.catalog.services.import_errors import ImportSourceError
from apps.catalog.services.sources.base import ExternalSourceAdapter

ADAPTERS: dict[str, type[ExternalSourceAdapter]] = {}


def register_adapter(adapter_class: type[ExternalSourceAdapter]) -> None:
    """Registra uma classe de conector pela sua chave estável."""
    ADAPTERS[adapter_class.key] = adapter_class


def get_adapter_class(key: str) -> type[ExternalSourceAdapter] | None:
    return ADAPTERS.get(key or "")


def get_adapter(
    source: CatalogSource,
    *,
    require_enabled: bool = True,
) -> ExternalSourceAdapter:
    adapter_class = get_adapter_class(source.adapter)
    if adapter_class is None:
        raise ImportSourceError(
            f"A fonte '{source.name}' não possui conector de importação externa."
        )
    if require_enabled and not source.enabled:
        raise ImportSourceError(f"A fonte '{source.name}' está desabilitada.")
    return adapter_class(source)


def available_sources() -> QuerySet[CatalogSource]:
    """Fontes habilitadas com conector registrado, usadas no formulário."""
    return CatalogSource.objects.filter(enabled=True, adapter__in=ADAPTERS)


def is_supported(source: CatalogSource) -> bool:
    return bool(source.adapter) and source.adapter in ADAPTERS
