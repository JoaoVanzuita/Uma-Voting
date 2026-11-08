"""Testes de configuração e agendamento de votações (US5)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.utils import timezone

from apps.core.exceptions import PreconditionError
from apps.voting.forms import VotingForm
from apps.voting.models import Mode, VotingEligibility, VotingStatus
from apps.voting.services.eligibility import (
    EligibilityError,
    add_eligible,
    remove_eligible,
)
from apps.voting.services.lifecycle import (
    VotingConfigError,
    VotingStateError,
    create_voting,
    evaluate_open_preconditions,
    schedule_voting,
    update_voting,
)
from tests.factories import (
    AdminUserFactory,
    CharacterFactory,
    CharacterVersionFactory,
    ParticipantFactory,
    VotingFactory,
)

pytestmark = pytest.mark.django_db


def base_data(**overrides):
    data = {
        "title": "Banimento de personagens",
        "description": "Votação de teste.",
        "catalog_cutoff_date": date(2026, 12, 1),
        "open_mode": Mode.MANUAL,
        "close_mode": Mode.MANUAL,
        "opens_at": None,
        "closes_at": None,
    }
    data.update(overrides)
    return data


def future(hours: int = 1):
    return timezone.now() + timedelta(hours=hours)


def add_catalog(count: int, cutoff=date(2026, 12, 1)) -> None:
    for index in range(count):
        character = CharacterFactory(
            stable_id=f"personagem-{index}",
            display_name=f"Personagem {index}",
        )
        CharacterVersionFactory(
            character=character,
            stable_id=f"personagem-{index}-v1",
            release_date_global=cutoff,
        )


# ---------------------------------------------------------------------------
# Modelo, serviço e formulário
# ---------------------------------------------------------------------------


def test_quantidade_padrao_de_escolhas_e_tres():
    admin = AdminUserFactory()

    voting = create_voting(base_data(), admin)

    assert voting.choices_count == 3
    assert voting.status == VotingStatus.DRAFT


def test_criacao_inclui_todos_os_usuarios_ativos_como_elegiveis():
    admin = AdminUserFactory()
    participant = ParticipantFactory()
    ParticipantFactory(is_active=False)

    voting = create_voting(base_data(), admin)

    eligible_ids = set(
        VotingEligibility.objects.filter(voting=voting).values_list("user_id", flat=True)
    )
    assert eligible_ids == {admin.pk, participant.pk}


def test_modo_automatico_exige_data_de_abertura():
    admin = AdminUserFactory()

    with pytest.raises(VotingConfigError, match="abertura"):
        create_voting(base_data(open_mode=Mode.AUTOMATIC), admin)


def test_modo_automatico_exige_data_de_encerramento():
    admin = AdminUserFactory()

    with pytest.raises(VotingConfigError, match="encerramento"):
        create_voting(
            base_data(open_mode=Mode.AUTOMATIC, close_mode=Mode.AUTOMATIC, opens_at=future()),
            admin,
        )


def test_modo_manual_aceita_datas_ausentes():
    admin = AdminUserFactory()

    voting = create_voting(base_data(), admin)

    assert voting.opens_at is None
    assert voting.closes_at is None


def test_modo_manual_aceita_datas_informativas():
    admin = AdminUserFactory()
    opens_at = future()
    closes_at = opens_at + timedelta(hours=2)

    voting = create_voting(
        base_data(opens_at=opens_at, closes_at=closes_at),
        admin,
    )

    assert voting.opens_at == opens_at
    assert voting.closes_at == closes_at


def test_datas_invertidas_sao_rejeitadas():
    admin = AdminUserFactory()
    opens_at = future()
    closes_at = opens_at - timedelta(minutes=1)

    with pytest.raises(VotingConfigError, match="posterior"):
        create_voting(base_data(opens_at=opens_at, closes_at=closes_at), admin)


def test_quantidade_de_escolhas_deve_ser_positiva():
    admin = AdminUserFactory()

    with pytest.raises(VotingConfigError, match="maior que zero"):
        create_voting(base_data(choices_count=0), admin)


def test_update_so_permitido_em_rascunho():
    voting = VotingFactory(status=VotingStatus.SCHEDULED)

    with pytest.raises(VotingStateError):
        update_voting(voting, base_data(title="Novo título"))


def test_update_nao_altera_created_by():
    admin = AdminUserFactory()
    voting = create_voting(base_data(), admin)
    other_admin = AdminUserFactory()

    update_voting(voting, {**base_data(title="Novo título"), "created_by": other_admin})

    voting.refresh_from_db()
    assert voting.created_by == admin
    assert voting.title == "Novo título"


def test_form_valida_modos_e_datas():
    automatic_without_dates = VotingForm(
        data={
            "title": "Automática",
            "choices_count": 3,
            "catalog_cutoff_date": "2026-12-01",
            "open_mode": Mode.AUTOMATIC,
            "close_mode": Mode.AUTOMATIC,
        }
    )
    assert not automatic_without_dates.is_valid()

    manual_without_dates = VotingForm(
        data={
            "title": "Manual",
            "choices_count": 3,
            "catalog_cutoff_date": "2026-12-01",
            "open_mode": Mode.MANUAL,
            "close_mode": Mode.MANUAL,
        }
    )
    assert manual_without_dates.is_valid()


def test_form_rejeita_datas_invertidas():
    form = VotingForm(
        data={
            "title": "Invertida",
            "choices_count": 3,
            "catalog_cutoff_date": "2026-12-01",
            "open_mode": Mode.MANUAL,
            "close_mode": Mode.MANUAL,
            "opens_at": "2026-12-01T12:00",
            "closes_at": "2026-12-01T11:00",
        }
    )

    assert not form.is_valid()
    assert "posterior" in str(form.errors)


# ---------------------------------------------------------------------------
# Elegíveis
# ---------------------------------------------------------------------------


def test_adicionar_e_remover_elegiveis_apenas_em_rascunho():
    voting = VotingFactory()
    participant = ParticipantFactory()

    assert add_eligible(voting, [participant.pk]) == 1
    assert VotingEligibility.objects.filter(voting=voting, user=participant).exists()

    assert remove_eligible(voting, [participant.pk]) == 1
    assert not VotingEligibility.objects.filter(voting=voting, user=participant).exists()

    voting.status = VotingStatus.SCHEDULED
    voting.save(update_fields=["status"])
    with pytest.raises(EligibilityError):
        add_eligible(voting, [participant.pk])
    with pytest.raises(EligibilityError):
        remove_eligible(voting, [participant.pk])


# ---------------------------------------------------------------------------
# Pré-condições e agendamento
# ---------------------------------------------------------------------------


def test_precondicoes_detectam_ausencia_de_elegiveis():
    voting = VotingFactory(choices_count=1)
    add_catalog(1)

    preconditions = evaluate_open_preconditions(voting)

    assert not preconditions.has_eligible
    assert not preconditions.ok


def test_precondicoes_detectam_catalogo_insuficiente():
    voting = VotingFactory(choices_count=3)
    ParticipantFactory()
    add_catalog(2)
    from apps.voting.services.eligibility import add_default_eligible

    add_default_eligible(voting)

    preconditions = evaluate_open_preconditions(voting)

    assert preconditions.has_eligible
    assert not preconditions.has_catalog
    assert not preconditions.ok


def test_agendar_exige_modo_automatico():
    voting = VotingFactory(open_mode=Mode.MANUAL)

    with pytest.raises(VotingConfigError, match="automático"):
        schedule_voting(voting)


def test_agendar_exige_abertura_no_futuro():
    voting = VotingFactory(
        open_mode=Mode.AUTOMATIC,
        opens_at=timezone.now() - timedelta(minutes=5),
        closes_at=future(),
    )

    with pytest.raises(VotingConfigError, match="futuro"):
        schedule_voting(voting)


def test_agendar_exige_elegiveis():
    voting = VotingFactory(
        open_mode=Mode.AUTOMATIC,
        opens_at=future(),
        closes_at=future(2),
        choices_count=1,
    )
    add_catalog(1)

    with pytest.raises(PreconditionError, match="elegíveis"):
        schedule_voting(voting)


def test_agendar_exige_catalogo_suficiente():
    voting = VotingFactory(
        open_mode=Mode.AUTOMATIC,
        opens_at=future(),
        closes_at=future(2),
        choices_count=3,
    )
    ParticipantFactory()
    from apps.voting.services.eligibility import add_default_eligible

    add_default_eligible(voting)
    add_catalog(2)

    with pytest.raises(PreconditionError, match="catálogo"):
        schedule_voting(voting)


def test_agendamento_bem_sucedido_bloqueia_configuracao():
    voting = VotingFactory(
        open_mode=Mode.AUTOMATIC,
        opens_at=future(),
        closes_at=future(2),
        choices_count=2,
    )
    ParticipantFactory()
    from apps.voting.services.eligibility import add_default_eligible

    add_default_eligible(voting)
    add_catalog(2)

    scheduled = schedule_voting(voting)

    scheduled.refresh_from_db()
    assert scheduled.status == VotingStatus.SCHEDULED
    with pytest.raises(VotingStateError):
        update_voting(scheduled, base_data(title="Outro"))
    with pytest.raises(EligibilityError):
        add_eligible(scheduled, [ParticipantFactory().pk])
