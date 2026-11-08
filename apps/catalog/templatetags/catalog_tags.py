"""Template tags de imagens do catálogo."""

from __future__ import annotations

from django import template
from django.conf import settings
from django.templatetags.static import static

from apps.catalog.models import Character, ImageAsset

register = template.Library()

PLACEHOLDER = "img/character-placeholder.webp"
PLACEHOLDER_ALT = "Imagem não disponível"


def _asset_url(asset: ImageAsset | None) -> str:
    if asset is None or asset.status != ImageAsset.Status.VALID or not asset.file_path:
        return static(PLACEHOLDER)
    return f"{settings.MEDIA_URL}{asset.file_path.lstrip('/')}"


@register.simple_tag
def character_image(character: Character | ImageAsset | None) -> str:
    """URL local da imagem principal válida, com placeholder como fallback."""
    if character is None:
        return static(PLACEHOLDER)

    if isinstance(character, ImageAsset):
        return _asset_url(character)

    asset = character.images.filter(
        is_current=True,
        status=ImageAsset.Status.VALID,
    ).first()
    return _asset_url(asset)


@register.simple_tag
def character_image_alt(character: Character | None) -> str:
    if character is None:
        return PLACEHOLDER_ALT
    return f"Imagem de {character.display_name}"
