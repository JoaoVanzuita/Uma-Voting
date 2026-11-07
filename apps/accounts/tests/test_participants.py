"""Testes unitários dos serviços de participantes."""

import pytest

from apps.accounts.models import User
from apps.accounts.services.participants import (
    ParticipantError,
    create_participant,
    deactivate_participant,
    update_participant,
)
from tests.factories import AdminUserFactory, ParticipantFactory

pytestmark = pytest.mark.django_db


def test_cria_participante_ativo_sem_senha_utilizavel():
    participant = create_participant("  SpecialWeek  ")

    assert participant.username == "SpecialWeek"
    assert participant.is_active is True
    assert participant.is_admin is False
    assert participant.has_usable_password() is False


def test_rejeita_username_vazio():
    with pytest.raises(ParticipantError):
        create_participant("   ")


def test_rejeita_username_maior_que_150():
    with pytest.raises(ParticipantError):
        create_participant("a" * 151)


def test_rejeita_duplicidade_case_insensitive():
    ParticipantFactory(username="TokaiTeio")

    with pytest.raises(ParticipantError):
        create_participant("tokaiteio")


def test_atualiza_username_preservando_conta():
    participant = ParticipantFactory(username="Antigo")

    updated = update_participant(participant, "NovoNome")

    updated.refresh_from_db()
    assert updated.username == "NovoNome"
    assert updated.is_active is True


def test_atualizacao_rejeita_duplicidade_case_insensitive():
    ParticipantFactory(username="Existente")
    participant = ParticipantFactory(username="Outro")

    with pytest.raises(ParticipantError):
        update_participant(participant, "existente")


def test_atualizacao_permite_mesmo_username_com_outra_caixa():
    participant = ParticipantFactory(username="SpecialWeek")

    updated = update_participant(participant, "specialweek")

    assert updated.username == "specialweek"


def test_administrador_nao_e_editavel_na_area_de_participantes():
    admin = AdminUserFactory()

    with pytest.raises(ParticipantError):
        update_participant(admin, "OutroNome")


def test_desativa_participante():
    participant = ParticipantFactory()

    deactivate_participant(participant)

    participant.refresh_from_db()
    assert participant.is_active is False


def test_desativacao_e_idempotente():
    participant = ParticipantFactory(is_active=False)

    deactivate_participant(participant)

    assert User.objects.get(pk=participant.pk).is_active is False


def test_administrador_nao_pode_ser_desativado_pela_area_de_participantes():
    admin = AdminUserFactory()

    with pytest.raises(ParticipantError):
        deactivate_participant(admin)

    admin.refresh_from_db()
    assert admin.is_active is True
