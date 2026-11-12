"""Factories compartilhadas para os testes (PostgreSQL real)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date

import factory
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone

from apps.catalog.models import (
    Aptitude,
    CatalogSource,
    Character,
    CharacterVersion,
    CharacterVersionAptitude,
    ImageAsset,
    ImportJob,
    SyncChange,
    SyncRun,
)
from apps.voting.models import (
    Ballot,
    BallotChoice,
    Mode,
    Voting,
    VotingCharacterSnapshot,
    VotingEligibility,
    VotingStatus,
    VotingVersionAptitudeSnapshot,
    VotingVersionSnapshot,
)

DEFAULT_ADMIN_PASSWORD = "senha-admin-teste"


@contextmanager
def fixture_seed():
    """Permite que factories criem elegíveis/snapshots em votações já abertas.

    O escape hatch existe apenas para dados de teste; a aplicação nunca define
    ``app.fixture_seed``. As triggers de produção continuam ativas.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT set_config('app.fixture_seed', 'on', false)")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.fixture_seed', 'off', false)")


class UserFactory(factory.django.DjangoModelFactory):
    """Participante padrão: ativo e sem senha utilizável."""

    class Meta:
        model = get_user_model()
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: f"participante{n}")
    is_admin = False
    is_active = True

    @factory.post_generation
    def password(self, create, extracted, **_kwargs):
        if not create:
            return
        if extracted:
            self.set_password(extracted)
        else:
            self.set_unusable_password()
        self.save(update_fields=["password"])


class ParticipantFactory(UserFactory):
    """Alias explícito para participantes."""

    is_admin = False


class AdminUserFactory(UserFactory):
    """Administrador com senha utilizável."""

    is_admin = True

    @factory.post_generation
    def password(self, create, extracted, **_kwargs):
        if not create:
            return
        self.set_password(extracted or DEFAULT_ADMIN_PASSWORD)
        self.save(update_fields=["password"])


class CatalogSourceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CatalogSource

    name = factory.Sequence(lambda n: f"fonte-{n}")
    kind = CatalogSource.Kind.FILE
    license_note = "Fonte de teste."
    enabled = True
    adapter = ""
    options = factory.LazyFunction(dict)


class ImportJobFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ImportJob

    source = factory.SubFactory(CatalogSourceFactory, adapter="test-source")
    kind = ImportJob.Kind.CATALOG
    status = ImportJob.Status.QUEUED
    phase = ImportJob.Phase.QUEUED
    options = factory.LazyFunction(dict)
    report = factory.LazyFunction(dict)


class SyncRunFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SyncRun

    source = factory.SubFactory(CatalogSourceFactory)
    status = SyncRun.Status.RUNNING
    summary = ""


class SyncChangeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SyncChange

    sync_run = factory.SubFactory(SyncRunFactory)
    change_type = SyncChange.ChangeType.NEW_CHARACTER
    status = SyncChange.Status.PENDING
    payload = factory.LazyFunction(dict)


class CharacterFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Character

    stable_id = factory.Sequence(lambda n: f"character-{n}")
    display_name = factory.Sequence(lambda n: f"Personagem {n}")


class CharacterVersionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterVersion

    character = factory.SubFactory(CharacterFactory)
    stable_id = factory.Sequence(lambda n: f"version-{n}")
    display_name = factory.Sequence(lambda n: f"Versão {n}")
    release_date_global = date(2025, 1, 1)


class AptitudeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Aptitude

    category = Aptitude.Category.STRATEGY
    value = factory.Sequence(lambda n: f"valor-{n}")
    label = factory.Sequence(lambda n: f"Valor {n}")


class CharacterVersionAptitudeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CharacterVersionAptitude

    version = factory.SubFactory(CharacterVersionFactory)
    aptitude = factory.SubFactory(AptitudeFactory)


class ImageAssetFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ImageAsset

    character = factory.SubFactory(CharacterFactory)
    file_path = factory.Sequence(lambda n: f"characters/character-{n}/image.webp")
    is_current = True
    status = ImageAsset.Status.VALID
    checksum_sha256 = factory.Sequence(lambda n: f"{n:064x}")
    width = 256
    height = 256
    source = None
    license_note = "Acervo local de teste."
    validated_at = factory.LazyFunction(timezone.now)


# ---------------------------------------------------------------------------
# Votações, snapshots e cédulas
# ---------------------------------------------------------------------------


class VotingFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Voting

    title = factory.Sequence(lambda n: f"Votação {n}")
    description = "Votação de teste."
    choices_count = 3
    catalog_cutoff_date = date(2026, 12, 1)
    open_mode = Mode.MANUAL
    close_mode = Mode.MANUAL
    status = VotingStatus.DRAFT
    created_by = factory.SubFactory(AdminUserFactory)


class OpenVotingFactory(VotingFactory):
    status = VotingStatus.OPEN
    opened_at = factory.LazyFunction(timezone.now)
    eligible_frozen_at = factory.LazyFunction(timezone.now)
    catalog_frozen_at = factory.LazyFunction(timezone.now)


class VotingEligibilityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VotingEligibility

    voting = factory.SubFactory(VotingFactory)
    user = factory.SubFactory(ParticipantFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with fixture_seed():
            return super()._create(model_class, *args, **kwargs)


class VotingCharacterSnapshotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VotingCharacterSnapshot

    voting = factory.SubFactory(OpenVotingFactory)
    source_character = factory.SubFactory(CharacterFactory)
    stable_id = factory.LazyAttribute(lambda obj: obj.source_character.stable_id)
    display_name = factory.LazyAttribute(lambda obj: obj.source_character.display_name)
    image_asset = None

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with fixture_seed():
            return super()._create(model_class, *args, **kwargs)


class VotingVersionSnapshotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VotingVersionSnapshot

    character_snapshot = factory.SubFactory(VotingCharacterSnapshotFactory)
    source_version = factory.SubFactory(
        CharacterVersionFactory,
        character=factory.SelfAttribute("..character_snapshot.source_character"),
    )
    stable_id = factory.LazyAttribute(lambda obj: obj.source_version.stable_id)
    release_date_global = factory.LazyAttribute(
        lambda obj: obj.source_version.release_date_global or date(2025, 1, 1)
    )

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with fixture_seed():
            return super()._create(model_class, *args, **kwargs)


class VotingVersionAptitudeSnapshotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VotingVersionAptitudeSnapshot

    version_snapshot = factory.SubFactory(VotingVersionSnapshotFactory)
    aptitude = factory.SubFactory(AptitudeFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        with fixture_seed():
            return super()._create(model_class, *args, **kwargs)


class BallotFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Ballot
        skip_postgeneration_save = True

    voting = factory.SubFactory(OpenVotingFactory)
    participant = factory.SubFactory(ParticipantFactory)

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        # A trigger de elegibilidade exige a linha antes do INSERT da cédula.
        with fixture_seed():
            VotingEligibility.objects.get_or_create(
                voting=kwargs["voting"],
                user=kwargs["participant"],
            )
        return super()._create(model_class, *args, **kwargs)

    @factory.post_generation
    def choices(self, create, extracted, **_kwargs):
        """Cria a quantidade exata de escolhas, salvo se ``choices=0``."""
        if not create:
            return
        count = self.voting.choices_count if extracted is None else int(extracted)
        for _ in range(count):
            BallotChoiceFactory(ballot=self)


class BallotChoiceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BallotChoice

    ballot = factory.SubFactory(BallotFactory)
    character_snapshot = factory.SubFactory(
        VotingCharacterSnapshotFactory,
        voting=factory.SelfAttribute("..ballot.voting"),
    )
