"""Testes de preservação de snapshots após mudanças no catálogo."""

from __future__ import annotations

from datetime import date

import pytest

from apps.catalog.models import (
    Aptitude,
    CharacterVersionAptitude,
    ImageAsset,
)
from apps.catalog.services.sync import approve_change, sync_from_file
from tests.factories import (
    AdminUserFactory,
    CatalogSourceFactory,
    CharacterFactory,
    CharacterVersionAptitudeFactory,
    CharacterVersionFactory,
    ImageAssetFactory,
    VotingCharacterSnapshotFactory,
    VotingVersionAptitudeSnapshotFactory,
    VotingVersionSnapshotFactory,
)

HEADER = (
    "character_stable_id,character_name,version_stable_id,version_name,"
    "release_date_global,strategy,distances,surfaces\n"
)


@pytest.mark.django_db
def test_mudancas_no_catalogo_nao_alteram_snapshots():
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    version = CharacterVersionFactory(
        character=character,
        stable_id="tokai-teio-original",
        display_name="Original",
        release_date_global=date(2025, 6, 26),
    )
    aptitude = Aptitude.objects.get(category="strategy", value="pace")
    CharacterVersionAptitudeFactory(version=version, aptitude=aptitude)
    image = ImageAssetFactory(character=character, is_current=True)

    snapshot = VotingCharacterSnapshotFactory(
        source_character=character,
        stable_id=character.stable_id,
        display_name=character.display_name,
        image_asset=image,
    )
    version_snapshot = VotingVersionSnapshotFactory(
        character_snapshot=snapshot,
        source_version=version,
        stable_id=version.stable_id,
        release_date_global=version.release_date_global,
    )
    aptitude_snapshot = VotingVersionAptitudeSnapshotFactory(
        version_snapshot=version_snapshot,
        aptitude=aptitude,
    )

    # Atualização direta do catálogo e troca da imagem corrente.
    character.display_name = "Tokai Teio Renomeada"
    character.save()
    version.display_name = "Renomeada"
    version.release_date_global = date(2025, 12, 24)
    version.save()
    CharacterVersionAptitude.objects.filter(version=version).delete()
    CharacterVersionAptitudeFactory(
        version=version,
        aptitude=Aptitude.objects.get(category="strategy", value="late"),
    )
    ImageAsset.objects.filter(pk=image.pk).update(is_current=False)
    ImageAssetFactory(character=character, is_current=True)

    snapshot.refresh_from_db()
    version_snapshot.refresh_from_db()
    aptitude_snapshot.refresh_from_db()

    assert snapshot.display_name == "Tokai Teio"
    assert snapshot.image_asset_id == image.pk
    assert version_snapshot.stable_id == "tokai-teio-original"
    assert version_snapshot.release_date_global == date(2025, 6, 26)
    assert aptitude_snapshot.aptitude_id == aptitude.pk


@pytest.mark.django_db
def test_aprovacao_de_sincronizacao_nao_alteram_snapshots(tmp_path):
    source = CatalogSourceFactory(name="curadoria-local")
    character = CharacterFactory(stable_id="tokai-teio", display_name="Tokai Teio")
    version = CharacterVersionFactory(
        character=character,
        stable_id="tokai-teio-original",
        display_name="Original",
        release_date_global=date(2025, 6, 26),
    )
    aptitude = Aptitude.objects.get(category="strategy", value="pace")
    CharacterVersionAptitudeFactory(version=version, aptitude=aptitude)

    snapshot = VotingCharacterSnapshotFactory(
        source_character=character,
        stable_id=character.stable_id,
        display_name=character.display_name,
    )
    version_snapshot = VotingVersionSnapshotFactory(
        character_snapshot=snapshot,
        source_version=version,
        stable_id=version.stable_id,
        release_date_global=version.release_date_global,
    )

    path = tmp_path / "catalog.csv"
    path.write_text(
        HEADER
        + "tokai-teio,Tokai Teio Renomeada,tokai-teio-original,Original,"
        "2025-06-26,pace,medium,turf\n",
        encoding="utf-8",
    )
    run = sync_from_file(str(path), source)
    admin = AdminUserFactory()
    for change in run.changes.filter(status="pending"):
        approve_change(change, admin)

    snapshot.refresh_from_db()
    version_snapshot.refresh_from_db()
    assert snapshot.display_name == "Tokai Teio"
    assert version_snapshot.stable_id == "tokai-teio-original"
    assert version_snapshot.release_date_global == date(2025, 6, 26)
