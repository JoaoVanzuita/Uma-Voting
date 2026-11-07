"""Testes de elegibilidade padrão das votações."""

import pytest

from apps.voting.models import VotingEligibility
from apps.voting.services.eligibility import add_default_eligible
from tests.factories import (
    AdminUserFactory,
    ParticipantFactory,
    UserFactory,
    VotingFactory,
)

pytestmark = pytest.mark.django_db


def test_inclui_todos_os_usuarios_ativos_inclusive_administradores():
    participant = ParticipantFactory()
    admin = AdminUserFactory()
    inactive = ParticipantFactory(is_active=False)
    voting = VotingFactory(created_by=admin)

    created = add_default_eligible(voting)

    assert created == 2
    eligible_ids = set(
        VotingEligibility.objects.filter(voting=voting).values_list("user_id", flat=True)
    )
    assert eligible_ids == {participant.pk, admin.pk}
    assert inactive.pk not in eligible_ids


def test_usuarios_cadastrados_depois_nao_entram_automaticamente():
    existing = ParticipantFactory()
    voting = VotingFactory()
    add_default_eligible(voting)

    later = UserFactory(username="CadastroPosterior")

    eligible_ids = set(
        VotingEligibility.objects.filter(voting=voting).values_list("user_id", flat=True)
    )
    assert existing.pk in eligible_ids
    assert later.pk not in eligible_ids


def test_operacao_e_idempotente():
    ParticipantFactory()
    voting = VotingFactory()

    first = add_default_eligible(voting)
    second = add_default_eligible(voting)

    assert first >= 1
    assert second == 0
    assert VotingEligibility.objects.filter(voting=voting).count() == first


def test_desativar_participante_nao_remove_elegibilidade_existente():
    from apps.accounts.services.participants import deactivate_participant

    participant = ParticipantFactory()
    voting = VotingFactory()
    add_default_eligible(voting)

    deactivate_participant(participant)

    assert VotingEligibility.objects.filter(voting=voting, user=participant).exists()
