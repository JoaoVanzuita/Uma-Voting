"""Contratos de apresentação do dashboard e da administração de votações (Fases 4–6)."""

from __future__ import annotations

import re
from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.catalog.models import ImageAsset
from apps.voting.models import VotingStatus
from apps.voting.services.ballots import submit_ballot
from apps.voting.services.eligibility import add_default_eligible
from apps.voting.services.lifecycle import cancel_voting, close_voting
from apps.voting.tests.helpers import create_open_voting
from tests.factories import (
    AdminUserFactory,
    CharacterFactory,
    CharacterVersionFactory,
    ImageAssetFactory,
    ParticipantFactory,
    SyncChangeFactory,
    VotingEligibilityFactory,
    VotingFactory,
)

pytestmark = pytest.mark.django_db


def add_catalog(count: int) -> None:
    for index in range(count):
        character = CharacterFactory(
            stable_id=f"ui-personagem-{index}",
            display_name=f"UI Personagem {index}",
        )
        CharacterVersionFactory(
            character=character,
            stable_id=f"ui-personagem-{index}-v1",
            release_date_global=date(2026, 12, 1),
        )


# ---------------------------------------------------------------------------
# D01 — Dashboard
# ---------------------------------------------------------------------------


def test_dashboard_mostra_seis_indicadores_e_remove_atalhos(client):
    admin = AdminUserFactory()
    client.force_login(admin)

    response = client.get(reverse("admin:dashboard"))
    body = response.content.decode()

    assert response.status_code == 200
    for label in (
        "Participantes ativos",
        "Votações abertas",
        "Votações agendadas",
        "Mudanças de catálogo pendentes",
        "Personagens sem imagem válida",
        "Imagens correntes inválidas",
    ):
        assert label in body
    assert "Saúde do catálogo" in body
    assert "Nova votação" in body
    assert "Atalhos" not in body


def test_dashboard_vazio_mantem_estados_vazios(client):
    admin = AdminUserFactory()
    client.force_login(admin)

    body = client.get(reverse("admin:dashboard")).content.decode()

    assert "Nenhuma votação aberta ou agendada no momento." in body
    assert "Nenhuma votação criada ainda." in body
    assert "Em dia" in body
    assert "Nada bloqueando a operação agora." in body
    assert "dashboard-section--attention" not in body


def test_dashboard_comeca_pela_acao_e_termina_na_saude_do_catalogo(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    SyncChangeFactory()
    ImageAssetFactory(status=ImageAsset.Status.INVALID, is_current=True)

    body = client.get(reverse("admin:dashboard")).content.decode()

    assert 'class="admin-content"' in body
    assert "admin-topbar__marker" in body
    assert body.index('id="actions-title"') < body.index('id="ongoing-title"')
    assert body.index('id="ongoing-title"') < body.index('id="metrics-title"')
    assert body.index('id="metrics-title"') < body.index('id="catalog-health-title"')
    assert "dashboard-section--attention" in body
    assert "2 pendências" in body
    assert "Revisar catálogo" in body
    assert reverse("admin:catalog_images") + "?status=invalid" in body
    assert body.count('class="dashboard-section__index"') == 4


def test_dashboard_explica_votacao_agendada_bloqueada(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(
        title="Agendada sem configuração",
        status=VotingStatus.SCHEDULED,
        opens_at=timezone.now() + timedelta(days=1),
    )

    body = client.get(reverse("admin:dashboard")).content.decode()

    assert "Agendada sem configuração" in body
    assert "A abertura automática está bloqueada por:" in body
    assert "A votação não possui participantes elegíveis." in body
    assert reverse("admin:voting_detail", args=[voting.pk]) in body


# ---------------------------------------------------------------------------
# V01 — Lista
# ---------------------------------------------------------------------------


def test_lista_exibe_cards_e_acoes_por_estado(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    draft = VotingFactory(title="Rascunho visível")
    open_voting = VotingFactory(title="Aberta visível", status=VotingStatus.OPEN)

    body = client.get(reverse("admin:voting_list")).content.decode()

    assert "Rascunho visível" in body
    assert "Aberta visível" in body
    assert "Acervo de votações" in body
    assert "editorial-list av-voting-list" in body
    assert body.count("editorial-item__index") >= 2
    assert reverse("admin:voting_edit", args=[draft.pk]) in body
    assert reverse("admin:voting_edit", args=[open_voting.pk]) not in body
    assert reverse("admin:voting_detail", args=[draft.pk]) in body


def test_lista_preserva_filtros_e_estado_vazio(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    VotingFactory(title="Votação existente")

    body = client.get(reverse("admin:voting_list"), {"q": "inexistente"}).content.decode()

    assert "Nenhuma votação encontrada" in body
    assert 'value="inexistente"' in body
    assert "Limpar filtros" in body


# ---------------------------------------------------------------------------
# V02 — Formulário
# ---------------------------------------------------------------------------


def test_formulario_agrupa_secoes_e_preserva_campos(client):
    admin = AdminUserFactory()
    client.force_login(admin)

    body = client.get(reverse("admin:voting_create")).content.decode()

    assert "Informações gerais" in body
    assert "Agendamento" in body
    assert "form-panel" in body
    assert "form-grid" in body
    assert body.count("form-section__index") == 2
    for field_name in (
        "title",
        "description",
        "choices_count",
        "catalog_cutoff_date",
        "open_mode",
        "opens_at",
        "close_mode",
        "closes_at",
    ):
        assert f'name="{field_name}"' in body


def test_formulario_exibe_erros_de_validacao(client):
    admin = AdminUserFactory()
    client.force_login(admin)

    response = client.post(
        reverse("admin:voting_create"),
        {
            "title": "",
            "description": "",
            "choices_count": 3,
            "catalog_cutoff_date": "2026-12-01",
            "open_mode": "automatic",
            "close_mode": "automatic",
            "opens_at": "",
            "closes_at": "",
        },
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert 'class="alert alert-danger"' in body
    assert "Informe o título da votação." in body
    assert "Este campo é obrigatório." in body


# ---------------------------------------------------------------------------
# V03 — Detalhe contextual
# ---------------------------------------------------------------------------


def test_detalhe_rascunho_pronto_oferece_abertura(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(status=VotingStatus.DRAFT, open_mode="manual", choices_count=2)
    add_default_eligible(voting)
    add_catalog(2)

    body = client.get(reverse("admin:voting_detail", args=[voting.pk])).content.decode()

    assert "Pré-condições de abertura" in body
    assert "Ação principal" in body
    assert "Zona de risco" in body
    assert "Abrir votação" in body
    assert reverse("admin:voting_open", args=[voting.pk]) in body
    assert "Abrir a votação agora? Os elegíveis e o catálogo serão congelados." in body


def test_detalhe_rascunho_automatico_oferece_agendamento(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(
        status=VotingStatus.DRAFT,
        open_mode="automatic",
        opens_at=timezone.now() + timedelta(hours=2),
        choices_count=2,
    )
    add_default_eligible(voting)
    add_catalog(2)

    body = client.get(reverse("admin:voting_detail", args=[voting.pk])).content.decode()

    assert "Agendar votação" in body
    assert reverse("admin:voting_schedule", args=[voting.pk]) in body


def test_detalhe_rascunho_bloqueado_nao_oferece_abertura(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(status=VotingStatus.DRAFT, open_mode="manual")

    body = client.get(reverse("admin:voting_detail", args=[voting.pk])).content.decode()

    assert "A votação não pode ser aberta" in body
    assert "Pendente" in body
    assert reverse("admin:voting_open", args=[voting.pk]) not in body


def test_detalhe_agendada_mostra_abertura_automatica(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(
        status=VotingStatus.SCHEDULED,
        open_mode="automatic",
        opens_at=timezone.now() + timedelta(hours=2),
    )

    body = client.get(reverse("admin:voting_detail", args=[voting.pk])).content.decode()

    assert "Abertura automática" in body
    assert "Acompanhamento" in body


def test_detalhe_aberta_exibe_parciais_e_exclusao_de_voto(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    submit_ballot(voting, participant, [snapshots[0].pk])

    body = client.get(reverse("admin:voting_detail", args=[voting.pk])).content.decode()

    assert "Ver resultados parciais" in body
    assert "Excluir voto" in body
    assert "poderá votar novamente" in body
    assert reverse("admin:voting_close", args=[voting.pk]) in body
    assert "Encerrar a votação? Novas cédulas serão bloqueadas." in body
    assert reverse("admin:ballot_delete", args=[voting.pk, participant.pk]) in body
    assert "Excluir a cédula deste participante? Ele poderá votar novamente." in body
    assert reverse("admin:voting_cancel", args=[voting.pk]) in body
    assert "Cancelar a votação? Todas as cédulas serão eliminadas definitivamente." in body
    assert participant.username in body
    assert snapshots[0].display_name not in body


def test_detalhe_encerrada_mostra_ranking_e_nao_permite_exclusao(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    submit_ballot(voting, participant, [snapshots[0].pk])
    close_voting(voting, "admin")
    voting.refresh_from_db()

    body = client.get(reverse("admin:voting_detail", args=[voting.pk])).content.decode()

    assert "Ver ranking final" in body
    assert "Disponível apenas com a votação aberta." in body
    assert "Excluir voto" not in body


def test_detalhe_cancelada_nao_oferece_reativacao(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    submit_ballot(voting, participant, [snapshots[0].pk])
    cancel_voting(voting, admin=admin)
    voting.refresh_from_db()

    body = client.get(reverse("admin:voting_detail", args=[voting.pk])).content.decode()

    assert "não pode ser reaberta" in body
    assert "não produz resultado oficial" in body
    assert reverse("admin:voting_cancel", args=[voting.pk]) not in body


# ---------------------------------------------------------------------------
# V04 — Participantes com acesso
# ---------------------------------------------------------------------------


def test_participantes_com_acesso_lista_inclusao_e_remocao(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(status=VotingStatus.DRAFT)
    participant = ParticipantFactory(username="Acesso Teste")
    VotingEligibilityFactory(voting=voting, user=participant)

    body = client.get(reverse("admin:voting_eligible", args=[voting.pk])).content.decode()

    assert "Participantes com acesso" in body
    assert "Adicionar elegíveis" in body
    assert "Acesso Teste" in body
    assert 'name="action" value="remove"' in body
    assert f'name="user_id" value="{participant.pk}"' in body


def test_participantes_com_acesso_fora_do_rascunho_redireciona(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(status=VotingStatus.OPEN)

    response = client.get(reverse("admin:voting_eligible", args=[voting.pk]))

    assert response.status_code == 302
    assert response.url == reverse("admin:voting_detail", args=[voting.pk])


# ---------------------------------------------------------------------------
# V05 — Resultados e privacidade
# ---------------------------------------------------------------------------


def test_resultados_parciais_sem_associacao_participante_personagem(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    submit_ballot(voting, participant, [snapshots[0].pk])

    body = client.get(reverse("admin:voting_results", args=[voting.pk])).content.decode()

    assert "Resultados parciais" in body
    assert "result-list--partial" in body
    assert snapshots[0].display_name in body
    assert participant.username not in body
    assert "participant_id" not in body


def test_resultados_finais_usam_ranking_e_dense_rank(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    submit_ballot(voting, participant, [snapshots[0].pk])
    close_voting(voting, "admin")

    body = client.get(reverse("admin:voting_results", args=[voting.pk])).content.decode()

    assert "Ranking final" in body
    assert "1º" in body
    assert "result-list--final" in body
    assert "result-item__bar" in body


def test_resultado_de_cancelada_nao_e_exibido(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=1)
    submit_ballot(voting, participant, [snapshots[0].pk])
    cancel_voting(voting, admin=admin)

    body = client.get(reverse("admin:voting_results", args=[voting.pk])).content.decode()

    assert "não possuem resultado oficial" in body
    assert snapshots[0].display_name not in body


# ---------------------------------------------------------------------------
# V06 — Participação
# ---------------------------------------------------------------------------


def test_participacao_resumo_badges_e_privacidade(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=1)
    pending = ParticipantFactory(username="Pendente Teste")
    VotingEligibilityFactory(voting=voting, user=pending)
    submit_ballot(voting, participant, [snapshots[0].pk])

    body = client.get(reverse("admin:voting_participation", args=[voting.pk])).content.decode()

    assert participant.username in body
    assert pending.username in body
    assert "Votou" in body
    assert "Pendente" in body
    assert "Não votou" in body
    assert snapshots[0].display_name not in body
    pending_match = re.search(r"Pendentes</p>\s*<p class=\"stat-card__value\">\s*(\d+)", body)
    assert pending_match is not None
    assert pending_match.group(1) == "1"


def test_participacao_sem_elegiveis_mostra_estado_vazio(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    voting = VotingFactory(status=VotingStatus.DRAFT)

    body = client.get(reverse("admin:voting_participation", args=[voting.pk])).content.decode()

    assert "Nenhum participante elegível." in body
