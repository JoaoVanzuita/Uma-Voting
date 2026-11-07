"""Factories compartilhadas para os testes (PostgreSQL real)."""

from __future__ import annotations

from datetime import date

import factory
from apps.catalog.models import (
    Aptitude,
    CatalogSource,
    Character,
    CharacterVersion,
    CharacterVersionAptitude,
    ImageAsset,
)
from django.contrib.auth import get_user_model
from django.utils import timezone

DEFAULT_ADMIN_PASSWORD = "senha-admin-teste"


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
