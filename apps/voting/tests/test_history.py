"""Testes de histórico do participante e painel administrativo (US8)."""

from __future__ import annotations

import pytest
from django.urls import reverse

from apps.accounts.models import User
from apps.catalog.models import ImageAsset, SyncChange, SyncRun
from apps.voting.models import VotingStatus
from apps.voting.services.ballots import submit_ballot
from apps.voting.services.lifecycle import close_voting
from apps.voting.tests.helpers import create_open_voting
from tests.factories import (
    AdminUserFactory,
    CatalogSourceFactory,
    CharacterFactory,
    ImageAssetFactory,
    OpenVotingFactory,
    ParticipantFactory,
    VotingEligibilityFactory,
    VotingFactory,
)

pytestmark = pytest.mark.django_db


def test_historico_separa_respondidas_e_encerradas_sem_resposta(client):
    participant = ParticipantFactory()

    answered_open, _p, snapshots = create_open_voting(choices_count=1, candidates=1)
    VotingEligibilityFactory(voting=answered_open, user=participant)
    submit_ballot(answered_open, participant, [snapshots[0].pk])

    answered_closed = OpenVotingFactory(title="Respondida encerrada")
    VotingEligibilityFactory(voting=answered_closed, user=participant)
    close_voting(answered_closed, "admin")

    closed_without = OpenVotingFactory(title="Encerrada sem resposta")
    VotingEligibilityFactory(voting=closed_without, user=participant)
    close_voting(closed_without, "admin")

    cancelled = VotingFactory(status=VotingStatus.CANCELLED, title="Cancelada")
    VotingEligibilityFactory(voting=cancelled, user=participant)

    not_eligible = OpenVotingFactory(title="Não elegível")

    client.force_login(participant)
    response = client.get(reverse("participant:history"))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Respondidas" in body
    assert "Encerradas sem resposta" in body
    assert answered_open.title in body
    assert answered_closed.title in body
    assert closed_without.title in body
    assert cancelled.title not in body
    assert not_eligible.title not in body


def test_historico_vazio(client):
    participant = ParticipantFactory()
    client.force_login(participant)

    response = client.get(reverse("participant:history"))

    body = response.content.decode()
    assert response.status_code == 200
    assert "Você ainda não respondeu nenhuma votação." in body
    assert "Nenhuma votação encerrada sem resposta." in body


def test_home_exibe_apenas_abertas_e_agendadas(client):
    participant = ParticipantFactory()
    open_voting = OpenVotingFactory(title="Aberta")
    scheduled = VotingFactory(status=VotingStatus.SCHEDULED, title="Agendada")
    closed = VotingFactory(status=VotingStatus.CLOSED, title="Encerrada")
    cancelled = VotingFactory(status=VotingStatus.CANCELLED, title="Cancelada")
    for voting in (open_voting, scheduled, closed, cancelled):
        VotingEligibilityFactory(voting=voting, user=participant)

    client.force_login(participant)
    response = client.get(reverse("participant:home"))

    body = response.content.decode()
    assert open_voting.title in body
    assert scheduled.title in body
    assert closed.title not in body
    assert cancelled.title not in body


def test_dashboard_exige_administrador(client):
    participant = ParticipantFactory()
    client.force_login(participant)

    response = client.get(reverse("admin:dashboard"))

    assert response.status_code == 403


def test_dashboard_exibe_indicadores_e_atalhos(client):
    admin = AdminUserFactory()
    ParticipantFactory()
    ParticipantFactory(is_active=False)
    VotingFactory(status=VotingStatus.OPEN, title="Votação aberta")
    VotingFactory(status=VotingStatus.SCHEDULED, title="Votação agendada")
    VotingFactory(status=VotingStatus.DRAFT, title="Rascunho recente")

    source = CatalogSourceFactory()
    run = SyncRun.objects.create(source=source)
    SyncChange.objects.create(
        sync_run=run,
        change_type=SyncChange.ChangeType.UPDATE_CHARACTER,
        status=SyncChange.Status.PENDING,
    )
    SyncChange.objects.create(
        sync_run=run,
        change_type=SyncChange.ChangeType.UPDATE_CHARACTER,
        status=SyncChange.Status.APPROVED,
    )

    CharacterFactory(stable_id="sem-imagem", display_name="Sem imagem")
    with_image = CharacterFactory(stable_id="com-imagem", display_name="Com imagem")
    ImageAssetFactory(character=with_image, is_current=True)
    invalid_character = CharacterFactory(stable_id="invalida", display_name="Inválida")
    ImageAssetFactory(
        character=invalid_character,
        is_current=True,
        status=ImageAsset.Status.INVALID,
    )

    client.force_login(admin)
    response = client.get(reverse("admin:dashboard"))

    body = response.content.decode()
    assert response.status_code == 200
    assert User.objects.filter(is_active=True).count() >= 2
    assert "Participantes ativos" in body
    assert "Votações abertas" in body
    assert "Votações agendadas" in body
    assert "Mudanças de catálogo pendentes" in body
    assert "Personagens sem imagem válida" in body
    assert "Imagens correntes inválidas" in body
    assert "Rascunho recente" in body
    assert reverse("admin:voting_create") in body
    assert reverse("admin:catalog_status") in body
    assert reverse("admin:participant_list") in body


def test_lista_administrativa_inclui_canceladas_e_filtro(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    cancelled = VotingFactory(status=VotingStatus.CANCELLED, title="Cancelada histórica")
    VotingFactory(status=VotingStatus.DRAFT, title="Rascunho oculto")

    response = client.get(reverse("admin:voting_list"))
    filtered = client.get(reverse("admin:voting_list"), {"status": "cancelled"})

    assert cancelled.title in response.content.decode()
    assert cancelled.title in filtered.content.decode()
    assert "Rascunho oculto" not in filtered.content.decode()
    assert "Cancelada" in filtered.content.decode()


def test_navegacao_de_historico_e_modo(client):
    admin = AdminUserFactory()
    client.force_login(admin)

    participant_page = client.get(reverse("participant:home"))
    admin_page = client.get(reverse("admin:dashboard"))

    assert reverse("participant:history") in participant_page.content.decode()
    assert reverse("admin:dashboard") in participant_page.content.decode()
    assert reverse("admin:voting_list") in admin_page.content.decode()
    assert reverse("admin:participant_mode") in admin_page.content.decode()
