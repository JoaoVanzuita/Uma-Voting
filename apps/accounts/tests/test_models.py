"""Testes fundamentais do modelo de usuário e do manager."""

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.models import User
from tests.factories import DEFAULT_ADMIN_PASSWORD, AdminUserFactory, UserFactory


@pytest.mark.django_db
def test_manager_busca_username_case_insensitive():
    user = UserFactory(username="SpecialWeek")

    assert User.objects.get_by_natural_key("specialweek") == user
    assert User.objects.get_by_natural_key("SPECIALWEEK") == user


@pytest.mark.django_db
def test_username_unico_case_insensitive():
    UserFactory(username="TokaiTeio")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            User.objects.create(username="tokaiteio")


@pytest.mark.django_db
def test_participante_recebe_senha_inutilizavel():
    participant = UserFactory()

    assert participant.is_active is True
    assert participant.is_admin is False
    assert participant.has_usable_password() is False


@pytest.mark.django_db
def test_administrador_tem_senha_utilizavel():
    admin = AdminUserFactory()

    assert admin.is_admin is True
    assert admin.has_usable_password() is True
    assert admin.check_password(DEFAULT_ADMIN_PASSWORD) is True


@pytest.mark.django_db
def test_manager_rejeita_username_vazio():
    with pytest.raises(ValueError):
        User.objects.create_user("   ")


@pytest.mark.django_db
def test_username_preserva_grafia_cadastrada():
    user = UserFactory(username="TokaiTeio")

    assert user.username == "TokaiTeio"
    assert user.display_name == "TokaiTeio"
