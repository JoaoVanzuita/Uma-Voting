"""Testes de integração do admin de configuração de votações (US5)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.formatting import format_datetime_br
from apps.voting.models import Mode, Voting, VotingEligibility, VotingStatus
from apps.voting.services.eligibility import add_default_eligible
from tests.factories import (
    AdminUserFactory,
    CharacterFactory,
    CharacterVersionFactory,
    ParticipantFactory,
    VotingFactory,
)

pytestmark = pytest.mark.django_db


def future(hours: int = 1):
    return timezone.now() + timedelta(hours=hours)


def add_catalog(count: int) -> None:
    for index in range(count):
        character = CharacterFactory(
            stable_id=f"personagem-{index}",
            display_name=f"Personagem {index}",
        )
        CharacterVersionFactory(
            character=character,
            stable_id=f"personagem-{index}-v1",
            release_date_global=date(2026, 12, 1),
        )


def form_payload(**overrides):
    payload = {
        "title": "Votação de banimento",
        "description": "Descrição",
        "choices_count": 3,
        "catalog_cutoff_date": "2026-12-01",
        "open_mode": Mode.MANUAL,
        "close_mode": Mode.MANUAL,
        "opens_at": "",
        "closes_at": "",
    }
    payload.update(overrides)
    return payload


def test_lista_exige_administrador(client):
    participant = ParticipantFactory()
    client.force_login(participant)

    response = client.get(reverse("admin:voting_list"))

    assert response.status_code == 403


def test_lista_exibe_votacoes(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    VotingFactory(title="Banimento de verão")

    response = client.get(reverse("admin:voting_list"))

    assert response.status_code == 200
    assert "Banimento de verão" in response.content.decode()


def test_formulario_de_criacao_usa_data_atual(client):
    admin = AdminUserFactory()
    client.force_login(admin)

    response = client.get(reverse("admin:voting_create"))

    assert response.status_code == 200
    assert response.context["form"].initial["catalog_cutoff_date"] == timezone.localdate()
    assert f'value="{timezone.localdate().isoformat()}"' in response.content.decode()


def test_criacao_manual_sem_datas(client):
    admin = AdminUserFactory()
    participant = ParticipantFactory()
    client.force_login(admin)

    response = client.post(reverse("admin:voting_create"), form_payload())

    voting = Voting.objects.get()
    assert response.status_code == 302
    assert voting.status == VotingStatus.DRAFT
    assert voting.catalog_cutoff_date == date(2026, 12, 1)
    assert voting.opens_at is None
    assert voting.closes_at is None
    assert VotingEligibility.objects.filter(voting=voting, user=admin).exists()
    assert VotingEligibility.objects.filter(voting=voting, user=participant).exists()


def test_criacao_automatica_sem_datas_e_rejeitada(client):
    admin = AdminUserFactory()
    client.force_login(admin)

    response = client.post(
        reverse("admin:voting_create"),
        form_payload(open_mode=Mode.AUTOMATIC, close_mode=Mode.AUTOMATIC),
    )

    assert response.status_code == 200
    assert not Voting.objects.exists()
    assert "obrigatória" in response.content.decode()


def test_edicao_em_rascunho(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(status=VotingStatus.DRAFT, title="Título antigo")

    response = client.post(
        reverse("admin:voting_edit", args=[voting.pk]),
        form_payload(title="Título novo"),
    )

    voting.refresh_from_db()
    assert response.status_code == 302
    assert voting.title == "Título novo"


def test_edicao_bloqueada_apos_agendamento(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(status=VotingStatus.SCHEDULED, title="Agendada")

    response = client.post(
        reverse("admin:voting_edit", args=[voting.pk]),
        form_payload(title="Alterada"),
    )

    voting.refresh_from_db()
    assert response.status_code == 302
    assert voting.title == "Agendada"


def test_detalhe_exibe_precondicoes_e_agendamento(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(
        open_mode=Mode.AUTOMATIC,
        opens_at=future(),
        closes_at=future(2),
        choices_count=2,
    )
    add_default_eligible(voting)
    add_catalog(2)

    response = client.get(reverse("admin:voting_detail", args=[voting.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Pré-condições de abertura" in body
    assert "Agendar votação" in body


def test_agendamento_pelo_admin(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(
        open_mode=Mode.AUTOMATIC,
        opens_at=future(),
        closes_at=future(2),
        choices_count=2,
    )
    add_default_eligible(voting)
    add_catalog(2)

    response = client.post(reverse("admin:voting_schedule", args=[voting.pk]))

    voting.refresh_from_db()
    assert response.status_code == 302
    assert voting.status == VotingStatus.SCHEDULED


def test_agendamento_sem_elegiveis_permanece_rascunho(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(
        open_mode=Mode.AUTOMATIC,
        opens_at=future(),
        closes_at=future(2),
        choices_count=1,
    )
    add_catalog(1)

    response = client.post(reverse("admin:voting_schedule", args=[voting.pk]), follow=True)

    voting.refresh_from_db()
    assert voting.status == VotingStatus.DRAFT
    assert "elegíveis" in response.content.decode()


def test_gerenciar_elegiveis_adiciona_e_remove(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(status=VotingStatus.DRAFT)
    participant = ParticipantFactory()

    response = client.post(
        reverse("admin:voting_eligible", args=[voting.pk]),
        {"action": "add", "users": [participant.pk]},
    )

    assert response.status_code == 302
    assert VotingEligibility.objects.filter(voting=voting, user=participant).exists()

    response = client.post(
        reverse("admin:voting_eligible", args=[voting.pk]),
        {"action": "remove", "user_id": participant.pk},
    )

    assert response.status_code == 302
    assert not VotingEligibility.objects.filter(voting=voting, user=participant).exists()


def test_pagina_de_elegiveis_exibe_formulario(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(status=VotingStatus.DRAFT)
    ParticipantFactory(username="Fulano")

    response = client.get(reverse("admin:voting_eligible", args=[voting.pk]))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Adicionar elegíveis" in body
    assert "Fulano" in body


def test_fluxo_completo_criacao_configuracao_e_agendamento(client):
    """Cenário do quickstart §5.3/§5.7 (parte de configuração) e SC-001."""
    admin = AdminUserFactory()
    participant = ParticipantFactory()
    client.force_login(admin)
    add_catalog(3)

    opens_at = future()
    closes_at = future(2)

    response = client.post(
        reverse("admin:voting_create"),
        form_payload(
            title="Fluxo completo",
            choices_count=2,
            open_mode=Mode.AUTOMATIC,
            close_mode=Mode.AUTOMATIC,
            opens_at=opens_at.strftime("%Y-%m-%dT%H:%M"),
            closes_at=closes_at.strftime("%Y-%m-%dT%H:%M"),
        ),
    )
    voting = Voting.objects.get()
    assert response.status_code == 302

    response = client.post(
        reverse("admin:voting_edit", args=[voting.pk]),
        form_payload(
            title="Fluxo completo ajustado",
            choices_count=2,
            open_mode=Mode.AUTOMATIC,
            close_mode=Mode.AUTOMATIC,
            opens_at=opens_at.strftime("%Y-%m-%dT%H:%M"),
            closes_at=closes_at.strftime("%Y-%m-%dT%H:%M"),
        ),
    )
    assert response.status_code == 302

    response = client.post(
        reverse("admin:voting_eligible", args=[voting.pk]),
        {"action": "add", "users": [participant.pk]},
    )
    assert response.status_code == 302

    response = client.post(reverse("admin:voting_schedule", args=[voting.pk]))

    voting.refresh_from_db()
    assert response.status_code == 302
    assert voting.status == VotingStatus.SCHEDULED
    assert voting.title == "Fluxo completo ajustado"
    assert VotingEligibility.objects.filter(voting=voting, user=participant).exists()


# ---------------------------------------------------------------------------
# Salvar e agendar na criação (US5 cenário 4)
# ---------------------------------------------------------------------------


def stamp(moment) -> str:
    """Formata no fuso local: o form interpreta o `datetime-local` em America/Sao_Paulo."""
    return timezone.localtime(moment).strftime("%Y-%m-%dT%H:%M")


def automatic_payload(**overrides):
    payload = form_payload(
        choices_count=2,
        open_mode=Mode.AUTOMATIC,
        close_mode=Mode.AUTOMATIC,
        opens_at=stamp(future()),
        closes_at=stamp(future(2)),
    )
    payload.update(overrides)
    return payload


def test_salvar_e_agendar_pelo_formulario_transiciona_para_scheduled(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    add_catalog(2)

    response = client.post(
        reverse("admin:voting_create"),
        automatic_payload(title="Agendamento direto", action="schedule"),
        follow=True,
    )

    voting = Voting.objects.get()
    assert response.redirect_chain[0][0] == reverse("admin:voting_detail", args=[voting.pk])
    assert voting.status == VotingStatus.SCHEDULED

    body = response.content.decode()
    assert 'class="alert alert-success"' in body
    assert "criada e agendada para" in body
    assert format_datetime_br(voting.opens_at) in body


def test_salvar_e_agendar_com_catalogo_insuficiente_persiste_rascunho(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    add_catalog(1)

    response = client.post(
        reverse("admin:voting_create"),
        automatic_payload(title="Catálogo curto", choices_count=3, action="schedule"),
        follow=True,
    )

    voting = Voting.objects.get()
    assert response.redirect_chain[0][0] == reverse("admin:voting_detail", args=[voting.pk])
    assert voting.status == VotingStatus.DRAFT

    body = response.content.decode()
    assert 'class="alert alert-warning"' in body
    assert "não agendada" in body
    assert "catálogo" in body
    assert "Revise e confirme o agendamento" in body


def test_salvar_e_agendar_em_modo_manual_persiste_rascunho(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    add_catalog(2)

    response = client.post(
        reverse("admin:voting_create"),
        form_payload(title="Manual agendado", action="schedule"),
        follow=True,
    )

    voting = Voting.objects.get()
    assert voting.status == VotingStatus.DRAFT

    body = response.content.decode()
    assert 'class="alert alert-warning"' in body
    assert "automático" in body


def test_salvar_rascunho_automatico_avisa_que_nao_foi_agendada(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    add_catalog(2)

    response = client.post(
        reverse("admin:voting_create"),
        automatic_payload(title="Só rascunho", action="draft"),
        follow=True,
    )

    voting = Voting.objects.get()
    assert voting.status == VotingStatus.DRAFT
    body = response.content.decode()
    assert 'class="alert alert-success"' in body
    assert "criada em rascunho, não agendada" in body


def test_post_sem_action_trata_como_rascunho(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    add_catalog(2)

    response = client.post(reverse("admin:voting_create"), automatic_payload(title="Sem action"))

    voting = Voting.objects.get()
    assert response.status_code == 302
    assert voting.status == VotingStatus.DRAFT


def test_agendar_com_formulario_invalido_nao_cria_votacao(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    add_catalog(2)

    response = client.post(
        reverse("admin:voting_create"),
        automatic_payload(title="", action="schedule"),
    )

    assert response.status_code == 200
    assert not Voting.objects.exists()
    assert 'class="alert alert-danger"' in response.content.decode()


def test_agendar_com_abertura_no_passado_nao_cria_votacao(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    add_catalog(2)

    response = client.post(
        reverse("admin:voting_create"),
        automatic_payload(
            title="Abertura vencida",
            opens_at=stamp(timezone.now() - timedelta(minutes=5)),
            action="schedule",
        ),
    )

    assert response.status_code == 200
    assert not Voting.objects.exists()
    assert "A data de abertura deve estar no futuro." in response.content.decode()


def test_agendamento_bloqueado_na_criacao_pode_ser_agendado_pelo_detalhe(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    add_catalog(3)

    response = client.post(
        reverse("admin:voting_create"),
        automatic_payload(title="Quatro escolhas", choices_count=4, action="schedule"),
    )
    voting = Voting.objects.get()
    assert response.status_code == 302
    assert voting.status == VotingStatus.DRAFT

    response = client.post(
        reverse("admin:voting_edit", args=[voting.pk]),
        automatic_payload(title="Quatro escolhas", choices_count=3),
    )
    assert response.status_code == 302

    response = client.post(reverse("admin:voting_schedule", args=[voting.pk]))

    voting.refresh_from_db()
    assert response.status_code == 302
    assert voting.status == VotingStatus.SCHEDULED
