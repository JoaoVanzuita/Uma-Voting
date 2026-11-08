"""Criação dos snapshots imutáveis de uma votação."""

from __future__ import annotations

import logging

from django.db import transaction

from apps.catalog.models import ImageAsset
from apps.catalog.services.queries import eligible_characters, eligible_versions
from apps.voting.models import (
    Voting,
    VotingCharacterSnapshot,
    VotingVersionAptitudeSnapshot,
    VotingVersionSnapshot,
)

logger = logging.getLogger("apps.voting.snapshots")


def create_snapshots(voting: Voting) -> int:
    """Copia personagens, versões e aptidões elegíveis para a votação.

    Somente versões com ``release_date_global <= catalog_cutoff_date`` entram.
    A imagem é o asset corrente válido no exato momento da abertura.
    """
    cutoff = voting.catalog_cutoff_date
    characters = (
        eligible_characters(cutoff).prefetch_related("versions", "images").order_by("display_name")
    )

    created = 0
    with transaction.atomic():
        for character in characters:
            versions = list(
                eligible_versions(character, cutoff).prefetch_related("version_aptitudes__aptitude")
            )
            if not versions:
                continue

            image = (
                character.images.filter(
                    is_current=True,
                    status=ImageAsset.Status.VALID,
                )
                .order_by("-created_at")
                .first()
            )

            character_snapshot = VotingCharacterSnapshot.objects.create(
                voting=voting,
                source_character=character,
                stable_id=character.stable_id,
                display_name=character.display_name,
                image_asset=image,
            )

            for version in versions:
                version_snapshot = VotingVersionSnapshot.objects.create(
                    character_snapshot=character_snapshot,
                    source_version=version,
                    stable_id=version.stable_id,
                    release_date_global=version.release_date_global,
                )
                VotingVersionAptitudeSnapshot.objects.bulk_create(
                    [
                        VotingVersionAptitudeSnapshot(
                            version_snapshot=version_snapshot,
                            aptitude=link.aptitude,
                        )
                        for link in version.version_aptitudes.all()
                    ]
                )

            created += 1

    logger.info(
        "Snapshots criados voting_id=%s characters=%s cutoff=%s",
        voting.pk,
        created,
        cutoff.isoformat(),
    )
    return created
