"""Consultas de elegibilidade e consolidação de aptidões do catálogo."""

from __future__ import annotations

from datetime import date

from django.db.models import QuerySet

from apps.catalog.models import (
    Aptitude,
    Character,
    CharacterVersion,
    CharacterVersionAptitude,
)


def eligible_versions(character: Character, cutoff: date) -> QuerySet[CharacterVersion]:
    """Versões lançadas no Global até a data de corte."""
    return character.versions.filter(release_date_global__lte=cutoff)


def is_eligible(character: Character, cutoff: date) -> bool:
    return eligible_versions(character, cutoff).exists()


def eligible_characters(cutoff: date) -> QuerySet[Character]:
    """Personagens com ao menos uma versão lançada até o corte."""
    return Character.objects.filter(versions__release_date_global__lte=cutoff).distinct()


def consolidated_aptitudes(character: Character, cutoff: date) -> set[Aptitude]:
    """União distinta das aptidões das versões elegíveis."""
    links = CharacterVersionAptitude.objects.filter(
        version__character=character,
        version__release_date_global__lte=cutoff,
    ).select_related("aptitude")
    return {link.aptitude for link in links}


def consolidated_aptitude_values(
    character: Character,
    cutoff: date,
) -> dict[str, list[str]]:
    """Aptidões consolidadas agrupadas por categoria e ordenadas."""
    grouped: dict[str, set[str]] = {}
    for aptitude in consolidated_aptitudes(character, cutoff):
        grouped.setdefault(aptitude.category, set()).add(aptitude.value)
    return {category: sorted(values) for category, values in grouped.items()}
