"""Testes de integração do fluxo de votação do participante."""

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.voting.models import Ballot, VotingStatus
from apps.voting.services.ballots import submit_ballot
from apps.voting.tests.helpers import (
    add_second_version,
    create_candidate,
    create_open_voting,
)
from tests.factories import (
    AdminUserFactory,
    OpenVotingFactory,
    ParticipantFactory,
    VotingEligibilityFactory,
)

pytestmark = pytest.mark.django_db


def _login(client, user):
    client.force_login(user)
    return client


# ---------------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------------


def test_home_lista_somente_votacoes_elegiveis_abertas_e_agendadas(client):
    participant = ParticipantFactory()
    open_voting = OpenVotingFactory(title="Aberta Elegível")
    scheduled = OpenVotingFactory(
        title="Agendada Elegível",
        status=VotingStatus.SCHEDULED,
        opens_at=timezone.now() + timedelta(days=1),
    )
    closed = OpenVotingFactory(title="Encerrada Elegível", status=VotingStatus.CLOSED)
    cancelled = OpenVotingFactory(title="Cancelada Elegível", status=VotingStatus.CANCELLED)
    OpenVotingFactory(title="Não Elegível")

    for voting in (open_voting, scheduled, closed, cancelled):
        VotingEligibilityFactory(voting=voting, user=participant)

    _login(client, participant)
    response = client.get(reverse("participant:home"))
    html = response.content.decode()

    assert response.status_code == 200
    assert "Aberta Elegível" in html
    assert "Agendada Elegível" in html
    assert "Encerrada Elegível" not in html
    assert "Cancelada Elegível" not in html
    assert "Não Elegível" not in html


def test_home_exibe_estado_vazio(client):
    participant = ParticipantFactory()
    _login(client, participant)

    response = client.get(reverse("participant:home"))

    assert response.status_code == 200
    assert "Nenhuma votação disponível" in response.content.decode()


def test_home_exige_autenticacao(client):
    response = client.get(reverse("participant:home"))

    assert response.status_code == 302


# ---------------------------------------------------------------------------
# Detalhe e grade
# ---------------------------------------------------------------------------


def test_detalhe_exige_elegibilidade(client):
    voting = OpenVotingFactory()
    outsider = ParticipantFactory()
    _login(client, outsider)

    response = client.get(reverse("participant:voting_detail", args=[voting.pk]))

    assert response.status_code == 403


def test_votacao_cancelada_retorna_404(client):
    voting = OpenVotingFactory(status=VotingStatus.CANCELLED)
    participant = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=participant)
    _login(client, participant)

    response = client.get(reverse("participant:voting_detail", args=[voting.pk]))

    assert response.status_code == 404


def test_detalhe_exibe_cards_e_filtros(client):
    voting, participant, snapshots = create_open_voting(candidates=3)
    _login(client, participant)

    response = client.get(reverse("participant:voting_detail", args=[voting.pk]))
    html = response.content.decode()

    assert response.status_code == 200
    for snapshot in snapshots:
        assert snapshot.display_name in html
    assert "Estratégia" in html
    assert "Distância" in html
    assert "Superfície" in html
    assert "Buscar personagem" in html
    assert "0 de 3 escolhas" in html


def test_grid_busca_por_nome(client):
    voting, participant, _snapshots = create_open_voting(candidates=3)
    _login(client, participant)

    response = client.get(
        reverse("participant:character_grid", args=[voting.pk]),
        {"q": "Personagem 1"},
    )
    html = response.content.decode()

    assert response.status_code == 200
    assert "Personagem 1" in html
    assert "Personagem 0" not in html
    assert "Personagem 2" not in html


def test_grid_aplica_or_dentro_da_categoria_e_and_entre_categorias(client):
    voting, participant, _snapshots = create_open_voting(candidates=0)
    create_candidate(
        voting, "Front Sprint Turf", strategy="front", distances=("sprint",), surfaces=("turf",)
    )
    create_candidate(
        voting, "Front Mile Turf", strategy="front", distances=("mile",), surfaces=("turf",)
    )
    create_candidate(
        voting, "Front Sprint Dirt", strategy="front", distances=("sprint",), surfaces=("dirt",)
    )
    _login(client, participant)

    response = client.get(
        reverse("participant:character_grid", args=[voting.pk]),
        {"distance": ["sprint", "mile"], "surface": ["turf"]},
    )
    html = response.content.decode()

    assert "Front Sprint Turf" in html
    assert "Front Mile Turf" in html
    assert "Front Sprint Dirt" not in html


def test_grid_exige_mesma_versao_para_categorias_diferentes(client):
    voting, participant, _snapshots = create_open_voting(candidates=0)
    snapshot = create_candidate(
        voting,
        "Cross Version",
        strategy="front",
        distances=("sprint",),
        surfaces=("turf",),
    )
    add_second_version(
        voting,
        snapshot,
        stable_suffix="v2",
        strategy="end",
        distances=("mile",),
        surfaces=("dirt",),
    )
    _login(client, participant)

    same_version = client.get(
        reverse("participant:character_grid", args=[voting.pk]),
        {"strategy": ["front"], "distance": ["sprint"]},
    ).content.decode()
    cross_version = client.get(
        reverse("participant:character_grid", args=[voting.pk]),
        {"strategy": ["front"], "surface": ["dirt"]},
    ).content.decode()

    assert "Cross Version" in same_version
    assert "Cross Version" not in cross_version


def test_grid_nao_duplica_personagem_com_multiplas_versoes(client):
    voting, participant, _snapshots = create_open_voting(candidates=0)
    snapshot = create_candidate(
        voting,
        "Duas Versões",
        strategy="front",
        distances=("sprint",),
        surfaces=("turf",),
    )
    add_second_version(
        voting,
        snapshot,
        stable_suffix="v2",
        strategy="front",
        distances=("mile",),
        surfaces=("turf",),
    )
    _login(client, participant)

    response = client.get(
        reverse("participant:character_grid", args=[voting.pk]),
        {"strategy": ["front"], "surface": ["turf"]},
    )
    html = response.content.decode()

    assert html.count("data-character-option") == 1


def test_grid_preserva_selecionados_e_contador(client):
    voting, participant, snapshots = create_open_voting(candidates=4)
    _login(client, participant)
    selected = snapshots[0]

    response = client.get(
        reverse("participant:character_grid", args=[voting.pk]),
        {"selected": [str(selected.pk)]},
    )
    html = response.content.decode()

    assert response.status_code == 200
    assert f'value="{selected.pk}"' in html
    assert "checked" in html
    assert "1 de 3 escolhas" in html


# ---------------------------------------------------------------------------
# Revisão e confirmação
# ---------------------------------------------------------------------------


def test_revisao_mostra_escolhas_e_aviso_de_definitiva(client):
    voting, participant, snapshots = create_open_voting(choices_count=3)
    _login(client, participant)

    response = client.post(
        reverse("participant:review", args=[voting.pk]),
        {"character_ids": [str(snapshot.pk) for snapshot in snapshots[:3]]},
    )
    html = response.content.decode()

    assert response.status_code == 200
    for snapshot in snapshots[:3]:
        assert snapshot.display_name in html
    assert "definitiva" in html


def test_revisao_com_quantidade_errada_retorna_400(client):
    voting, participant, snapshots = create_open_voting(choices_count=3)
    _login(client, participant)

    response = client.post(
        reverse("participant:review", args=[voting.pk]),
        {"character_ids": [str(snapshot.pk) for snapshot in snapshots[:2]]},
    )

    assert response.status_code == 400
    assert "Selecione exatamente 3 personagens." in response.content.decode()


def test_revisao_exige_post(client):
    voting, participant, _snapshots = create_open_voting()
    _login(client, participant)

    response = client.get(reverse("participant:review", args=[voting.pk]))

    assert response.status_code == 405


def test_confirmacao_cria_cedula_e_redireciona_para_consulta(client):
    voting, participant, snapshots = create_open_voting(choices_count=3)
    _login(client, participant)

    response = client.post(
        reverse("participant:confirm", args=[voting.pk]),
        {"character_ids": [str(snapshot.pk) for snapshot in snapshots[:3]]},
        follow=True,
    )
    html = response.content.decode()

    assert response.status_code == 200
    assert Ballot.objects.filter(voting=voting, participant=participant).exists()
    assert "Voto registrado com sucesso." in html
    assert "definitiva" in html
    for snapshot in snapshots[:3]:
        assert snapshot.display_name in html


def test_segundo_envio_retorna_409(client):
    voting, participant, snapshots = create_open_voting(choices_count=3)
    ids = [str(snapshot.pk) for snapshot in snapshots[:3]]
    _login(client, participant)
    client.post(reverse("participant:confirm", args=[voting.pk]), {"character_ids": ids})

    response = client.post(
        reverse("participant:confirm", args=[voting.pk]),
        {"character_ids": ids},
    )

    assert response.status_code == 409
    assert "Você já registrou um voto" in response.content.decode()
    assert Ballot.objects.filter(voting=voting, participant=participant).count() == 1


def test_confirmacao_com_quantidade_errada_retorna_400(client):
    voting, participant, snapshots = create_open_voting(choices_count=3)
    _login(client, participant)

    response = client.post(
        reverse("participant:confirm", args=[voting.pk]),
        {"character_ids": [str(snapshot.pk) for snapshot in snapshots[:2]]},
    )

    assert response.status_code == 400
    assert "Selecione exatamente 3 personagens." in response.content.decode()


def test_cedula_propria_nao_expoe_escolhas_de_outro_participante(client):
    voting, participant, snapshots = create_open_voting(choices_count=3, candidates=6)
    other = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=other)

    submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:3]])
    submit_ballot(voting, other, [snapshot.pk for snapshot in snapshots[3:6]])

    _login(client, participant)
    response = client.get(reverse("participant:ballot", args=[voting.pk]))
    html = response.content.decode()

    for snapshot in snapshots[:3]:
        assert snapshot.display_name in html
    for snapshot in snapshots[3:6]:
        assert snapshot.display_name not in html


def test_detalhe_encerrado_redireciona_para_cedula_existente(client):
    voting, participant, snapshots = create_open_voting(choices_count=3)

    submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:3]])
    voting.status = VotingStatus.CLOSED
    voting.save(update_fields=["status"])

    _login(client, participant)
    response = client.get(reverse("participant:voting_detail", args=[voting.pk]))

    assert response.status_code == 302
    assert response.url == reverse("participant:ballot", args=[voting.pk])


# ---------------------------------------------------------------------------
# Administrador elegível no modo participante
# ---------------------------------------------------------------------------


def test_admin_elegivel_vota_no_modo_participante_e_mantem_privacidade(client):
    admin = AdminUserFactory()
    voting, _participant, snapshots = create_open_voting(choices_count=3)
    VotingEligibilityFactory(voting=voting, user=admin)
    _login(client, admin)

    switch = client.post(reverse("admin:participant_mode"))
    assert switch.status_code == 302

    detail = client.get(reverse("participant:voting_detail", args=[voting.pk]))
    assert detail.status_code == 200

    confirm = client.post(
        reverse("participant:confirm", args=[voting.pk]),
        {"character_ids": [str(snapshot.pk) for snapshot in snapshots[:3]]},
    )
    assert confirm.status_code == 302

    ballot = client.get(reverse("participant:ballot", args=[voting.pk]))
    assert ballot.status_code == 200
    assert "Resultado" not in ballot.content.decode()

    dashboard = client.get(reverse("admin:dashboard"))
    dashboard_html = dashboard.content.decode()
    assert dashboard.status_code == 200
    for snapshot in snapshots[:3]:
        assert snapshot.display_name not in dashboard_html
