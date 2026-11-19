"""Busca e filtros de personagens dentro do snapshot de uma votação."""

from __future__ import annotations

from apps.voting.models import (
    Voting,
    VotingCharacterSnapshot,
    VotingVersionSnapshot,
)

FILTER_CATEGORIES = ("strategy", "distance", "surface")


def _selected_positions(selected_ids) -> dict[int, int]:
    """Posição 1-based de cada escolha, preservando a ordem de clique."""
    positions: dict[int, int] = {}
    for value in selected_ids or []:
        try:
            pk = int(value)
        except TypeError, ValueError:
            continue
        if pk not in positions:
            positions[pk] = len(positions) + 1
    return positions


def search_characters(
    voting: Voting,
    filters: dict[str, list[str]] | None = None,
    query: str = "",
    selected_ids=None,
) -> list[VotingCharacterSnapshot]:
    """Retorna personagens distintas, com filtros de mesma versão.

    Dentro de uma categoria os valores são OR; entre categorias, uma mesma
    versão precisa satisfazer todos os critérios.
    """
    filters = filters or {}
    queryset = VotingCharacterSnapshot.objects.filter(voting=voting).select_related("image_asset")

    if query:
        queryset = queryset.filter(display_name__icontains=query.strip())

    version_queryset = VotingVersionSnapshot.objects.filter(character_snapshot__voting=voting)

    for category in FILTER_CATEGORIES:
        values = [value for value in filters.get(category, []) if value]
        if not values:
            continue
        version_queryset = version_queryset.filter(
            aptitude_snapshots__aptitude__category=category,
            aptitude_snapshots__aptitude__value__in=values,
        )

    if filters:
        queryset = queryset.filter(version_snapshots__in=version_queryset)

    positions = _selected_positions(selected_ids)
    characters = list(queryset.distinct().order_by("display_name"))
    for character in characters:
        character.selection_order = positions.get(character.pk)
        character.selected = character.selection_order is not None
    return characters
