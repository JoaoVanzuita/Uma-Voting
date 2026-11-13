"""Testes de apresentação do fluxo do participante (Fase 3).

Cobrem apenas contratos visuais/estruturais introduzidos ou preservados pela
refatoração. Regras de negócio continuam cobertas pelos testes existentes.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.voting.models import VotingStatus
from apps.voting.services.ballots import submit_ballot
from apps.voting.services.lifecycle import close_voting
from apps.voting.tests.helpers import create_candidate, create_open_voting
from tests.factories import (
    OpenVotingFactory,
    ParticipantFactory,
    VotingEligibilityFactory,
)

pytestmark = pytest.mark.django_db


def _login(client, user):
    client.force_login(user)
    return client


# ---------------------------------------------------------------------------
# A01/A02 — autenticação
# ---------------------------------------------------------------------------


def test_login_de_participante_e_compacto_e_preserva_aviso_de_identidade(client):
    response = client.get(reverse("participant:login"))
    html = response.content.decode()

    assert response.status_code == 200
    assert "auth-shell--participant" in html
    assert "auth-brand" in html
    assert 'id="id_username"' in html
    assert 'name="username"' in html
    assert "Este acesso identifica apenas o username; não comprova sua identidade." in html
    assert reverse("admin:login") in html


def test_login_administrativo_compartilha_o_card_compacto(client):
    response = client.get(reverse("admin:login"))
    html = response.content.decode()

    assert response.status_code == 200
    assert 'class="auth-shell"' in html
    assert "auth-card" in html
    assert 'id="id_username"' in html
    assert 'id="id_password"' in html
    assert reverse("participant:login") in html


# ---------------------------------------------------------------------------
# P01 — home
# ---------------------------------------------------------------------------


def test_home_diferencia_abertas_e_agendadas_e_mantem_acoes(client):
    participant = ParticipantFactory()
    opened = OpenVotingFactory(title="Aberta visual")
    scheduled = OpenVotingFactory(
        title="Agendada visual",
        status=VotingStatus.SCHEDULED,
        opens_at=timezone.now() + timedelta(days=2),
    )
    for voting in (opened, scheduled):
        VotingEligibilityFactory(voting=voting, user=participant)

    _login(client, participant)
    html = client.get(reverse("participant:home")).content.decode()

    assert "voting-card--open" in html
    assert "voting-card--scheduled" in html
    assert "Aberta visual" in html
    assert "Agendada visual" in html
    assert "Votar agora" in html
    assert "Ver detalhes" in html
    assert "Abre em" in html


def test_home_destaca_a_aberta_com_encerramento_mais_proximo(client):
    participant = ParticipantFactory()
    now = timezone.now()
    featured = OpenVotingFactory(
        title="Aberta com prazo próximo",
        closes_at=now + timedelta(days=1),
    )
    other = OpenVotingFactory(
        title="Aberta com prazo distante",
        closes_at=now + timedelta(days=7),
    )
    scheduled = OpenVotingFactory(
        title="Agendada visual",
        status=VotingStatus.SCHEDULED,
        opens_at=now + timedelta(hours=2),
    )
    for voting in (featured, other, scheduled):
        VotingEligibilityFactory(voting=voting, user=participant)

    _login(client, participant)
    response = client.get(reverse("participant:home"))
    html = response.content.decode()

    assert response.context["featured_voting"] == featured
    assert response.context["other_votings"] == [other, scheduled]
    assert "home-featured" in html
    assert "card--list" in html
    assert "stage-band--open" in html
    assert html.count("card card--featured") == 1


def test_home_usa_agendada_como_destaque_quando_nao_ha_aberta(client):
    participant = ParticipantFactory()
    now = timezone.now()
    later = OpenVotingFactory(
        title="Agendada mais distante",
        status=VotingStatus.SCHEDULED,
        opens_at=now + timedelta(days=5),
    )
    featured = OpenVotingFactory(
        title="Agendada mais próxima",
        status=VotingStatus.SCHEDULED,
        opens_at=now + timedelta(days=1),
    )
    for voting in (later, featured):
        VotingEligibilityFactory(voting=voting, user=participant)

    _login(client, participant)
    response = client.get(reverse("participant:home"))
    html = response.content.decode()

    assert response.context["featured_voting"] == featured
    assert response.context["other_votings"] == [later]
    assert "stage-band--scheduled" in html
    assert "Ver detalhes" in html


def test_home_vazio_oferece_acesso_ao_historico(client):
    participant = ParticipantFactory()
    _login(client, participant)

    html = client.get(reverse("participant:home")).content.decode()

    assert "Nenhuma votação disponível" in html
    assert reverse("participant:history") in html


# ---------------------------------------------------------------------------
# P02/P03 — seleção
# ---------------------------------------------------------------------------


def test_selecao_preserva_contratos_de_htmx_ids_e_selecao(client):
    voting, participant, snapshots = create_open_voting(candidates=5)
    _login(client, participant)
    selected = snapshots[0]

    html = client.get(
        reverse("participant:voting_detail", args=[voting.pk]),
        {"selected": [str(selected.pk)]},
    ).content.decode()

    # Contrato HTMX exato.
    assert 'id="character-search"' in html
    assert 'hx-target="#character-grid"' in html
    assert 'hx-swap="innerHTML"' in html
    assert 'hx-trigger="input changed delay:300ms, search"' in html
    assert 'hx-include="closest form"' in html

    # Contrato de seleção.
    assert 'id="character-grid"' in html
    assert "data-selection-form" in html
    assert 'data-max-choices="3"' in html
    assert 'name="character_ids"' in html
    assert "data-character-option" in html
    assert "data-selected=" in html
    assert "data-disabled=" in html
    assert "data-selected-inputs" in html
    hidden_section = html.split("data-selected-inputs", 1)[1].split("</div>", 1)[0]
    assert 'name="selected"' in hidden_section
    assert f'value="{selected.pk}"' in hidden_section
    assert f'data-character-name="{selected.display_name}"' in hidden_section

    # Resumo persistente e linguagem.
    assert 'id="selection-summary"' in html
    assert "data-selection-counter" in html
    assert "data-selection-status" in html
    assert 'aria-live="polite"' in html
    assert "1 de 3 escolhas" in html
    assert "Revisar escolhas" in html


def test_grid_fragmento_mantem_oob_e_aria_live(client):
    voting, participant, snapshots = create_open_voting(candidates=3)
    _login(client, participant)

    html = client.get(
        reverse("participant:character_grid", args=[voting.pk]),
        {"selected": [str(snapshots[0].pk)]},
    ).content.decode()

    assert 'hx-swap-oob="true"' in html
    assert 'id="selection-summary"' in html
    assert "1 de 3 escolhas" in html
    assert 'aria-label="Personagens disponíveis"' in html


def test_filtros_sao_recolhiveis_e_exibem_chips_ativos(client):
    voting, participant, _snapshots = create_open_voting(candidates=0)
    selected = create_candidate(
        voting,
        "Front visual",
        strategy="front",
        distances=("sprint",),
        surfaces=("turf",),
    )
    _login(client, participant)

    html = client.get(
        reverse("participant:voting_detail", args=[voting.pk]),
        {"strategy": ["front"], "selected": [str(selected.pk)]},
    ).content.decode()

    assert "<details" in html
    assert "filter-panel" in html
    assert "Estratégia" in html
    assert "Distância" in html
    assert "Superfície" in html
    assert "data-filter-chip" in html
    assert "Remover filtro Front" in html
    assert "Limpar busca e filtros" in html
    # O chip ativo e o link de limpeza preservam a seleção na URL.
    assert f"selected={selected.pk}" in html


def test_limite_de_selecao_aparece_no_resumo(client):
    voting, participant, snapshots = create_open_voting(candidates=5)
    _login(client, participant)

    html = client.get(
        reverse("participant:character_grid", args=[voting.pk]),
        {"selected": [str(snapshot.pk) for snapshot in snapshots[:3]]},
    ).content.decode()

    assert "3 de 3 escolhas" in html
    assert 'data-limit-reached="true"' in html
    assert "Limite atingido. Desmarque uma escolha para alterar." in html


def test_selecao_preserva_ordem_e_numera_as_escolhas(client):
    voting, participant, snapshots = create_open_voting(choices_count=3, candidates=5)
    _login(client, participant)
    chosen = [snapshots[2], snapshots[0], snapshots[1]]

    response = client.get(
        reverse("participant:voting_detail", args=[voting.pk]),
        {"selected": [str(snapshot.pk) for snapshot in chosen]},
    )
    html = response.content.decode()

    assert response.context["selected_snapshots"] == chosen
    assert response.context["selected_ids"] == [snapshot.pk for snapshot in chosen]

    hidden_section = html.split("data-selected-inputs", 1)[1].split("</div>", 1)[0]
    positions = [hidden_section.index(f'value="{snapshot.pk}"') for snapshot in chosen]
    assert positions == sorted(positions)

    for index, snapshot in enumerate(chosen, start=1):
        assert f'aria-label="{snapshot.display_name} — Escolha {index}"' in html
        assert f'data-character-name="{snapshot.display_name}"' in hidden_section


def test_resumo_mostra_ate_tres_miniaturas_e_contador(client):
    voting, participant, snapshots = create_open_voting(choices_count=5, candidates=6)
    _login(client, participant)
    chosen = snapshots[:4]

    response = client.get(
        reverse("participant:character_grid", args=[voting.pk]),
        {"selected": [str(snapshot.pk) for snapshot in chosen]},
    )
    html = response.content.decode()

    assert response.context["selected_preview"] == chosen[:3]
    assert response.context["selected_more_count"] == 1
    assert html.count('class="selection-summary__thumb"') == 3
    assert 'class="selection-summary__more">+1</span>' in html
    # O limite não remove opções do grid.
    assert html.count('name="character_ids"') == 6


def test_revisao_respeita_ordem_dos_inputs_ocultos(client):
    voting, participant, snapshots = create_open_voting(choices_count=3, candidates=5)
    _login(client, participant)
    chosen = [snapshots[2], snapshots[0], snapshots[1]]

    response = client.post(
        reverse("participant:review", args=[voting.pk]),
        {
            "selected": [str(snapshot.pk) for snapshot in chosen],
            "character_ids": [str(snapshot.pk) for snapshot in snapshots[:3]],
        },
    )

    assert response.status_code == 200
    assert response.context["snapshots"] == chosen


def test_grid_de_votacao_encerrada_retorna_409_e_resumo_oob(client):
    voting, participant, _snapshots = create_open_voting(candidates=2)
    close_voting(voting, "admin")
    _login(client, participant)

    response = client.get(reverse("participant:character_grid", args=[voting.pk]))
    html = response.content.decode()

    assert response.status_code == 409
    assert "Esta votação não está aberta." in html
    assert 'hx-swap-oob="true"' in html


def test_detalhe_agendado_explica_que_a_votacao_ainda_nao_abriu(client):
    participant = ParticipantFactory()
    voting = OpenVotingFactory(
        title="Agendada em breve",
        status=VotingStatus.SCHEDULED,
        opens_at=timezone.now() + timedelta(days=1),
    )
    VotingEligibilityFactory(voting=voting, user=participant)
    _login(client, participant)

    html = client.get(reverse("participant:voting_detail", args=[voting.pk])).content.decode()

    assert "Esta votação ainda não está aberta" in html
    assert "A abertura está prevista para" in html
    assert reverse("participant:home") in html
    assert 'id="character-grid"' not in html


# ---------------------------------------------------------------------------
# P04/P05 — revisão e meu voto
# ---------------------------------------------------------------------------


def test_revisao_usa_linguagem_nova_e_preserva_confirmacao(client):
    voting, participant, snapshots = create_open_voting(choices_count=3)
    _login(client, participant)

    html = client.post(
        reverse("participant:review", args=[voting.pk]),
        {"character_ids": [str(snapshot.pk) for snapshot in snapshots[:3]]},
    ).content.decode()

    assert "Revisar escolhas" in html
    assert "A confirmação é definitiva" in html
    assert "Confirmar voto" in html
    assert "Voltar e ajustar" in html
    assert reverse("participant:confirm", args=[voting.pk]) in html
    assert "review-shell" in html
    assert "stage-band stage-band--open" in html
    assert "review-list--ordered" in html
    assert "portrait-frame--md" in html
    assert "Escolha 1 de 3" in html
    for snapshot in snapshots[:3]:
        assert snapshot.display_name in html
        assert f'name="character_ids" value="{snapshot.pk}"' in html


def test_meu_voto_aberto_nao_oferece_edicao_nem_resultado(client):
    voting, participant, snapshots = create_open_voting(choices_count=3)
    submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:3]])
    _login(client, participant)

    html = client.get(reverse("participant:ballot", args=[voting.pk])).content.decode()

    assert "Meu voto" in html
    assert "Voto registrado" in html
    assert "Registrado em" in html
    assert "definitiva" in html
    assert "Escolhas registradas" in html
    assert "Definitivo" in html
    assert "stage-band stage-band--open" in html
    assert "portrait-frame--md" in html
    assert "Confirmar voto" not in html
    assert "Reenviar" not in html
    assert "Ver resultado" not in html


def test_meu_voto_encerrado_oferece_resultado(client):
    voting, participant, snapshots = create_open_voting(choices_count=3)
    submit_ballot(voting, participant, [snapshot.pk for snapshot in snapshots[:3]])
    close_voting(voting, "admin")
    _login(client, participant)

    html = client.get(reverse("participant:ballot", args=[voting.pk])).content.decode()

    assert "Ver resultado" in html
    assert reverse("participant:result", args=[voting.pk]) in html
    assert "stage-band stage-band--closed" in html


# ---------------------------------------------------------------------------
# P06/P07/P08 — resultado, histórico e indisponibilidade
# ---------------------------------------------------------------------------


def test_resultado_mantem_dense_rank_empate_e_barra_proporcional(client):
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=3)
    other = ParticipantFactory()
    non_voter = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=other)
    VotingEligibilityFactory(voting=voting, user=non_voter)

    submit_ballot(voting, participant, [snapshots[0].pk])
    submit_ballot(voting, other, [snapshots[0].pk])
    close_voting(voting, "admin")
    _login(client, participant)

    response = client.get(reverse("participant:result", args=[voting.pk]))
    html = response.content.decode()

    assert response.context["participation"].ballots == 2
    assert response.context["participation"].eligible == 3
    assert response.context["participation"].percent == 67
    assert "Ranking final" in html
    assert "1º" in html
    assert "2 votos" in html
    assert "<progress" in html
    assert 'max="2"' in html
    assert 'value="2"' in html
    assert "Meu voto" in html
    assert "result-item__media" in html
    assert "result-list--final" in html
    assert "result-item--leader" in html
    assert "result-item__accent" in html
    assert "cédulas registradas" in html
    assert "(<strong>67%</strong>)" in html
    assert f'aria-label="{snapshots[0].display_name}: 2 votos de 2 do primeiro colocado"' in html


def test_resultado_vazio_mostra_estado_claro(client):
    voting, participant, _snapshots = create_open_voting(choices_count=1, candidates=2)
    close_voting(voting, "admin")
    _login(client, participant)

    response = client.get(reverse("participant:result", args=[voting.pk]))
    html = response.content.decode()

    assert response.context["participation"].ballots == 0
    assert response.context["participation"].eligible == 1
    assert response.context["participation"].percent == 0
    assert "Nenhum voto registrado" in html
    assert "sem votos válidos" in html
    assert "cédulas registradas" in html
    assert "(<strong>0%</strong>)" in html


def test_historico_usa_secoes_novas_e_mantem_estados_vazios(client):
    participant = ParticipantFactory()
    _login(client, participant)

    html = client.get(reverse("participant:history")).content.decode()

    assert "Respondidas" in html
    assert "Encerradas sem voto" in html
    assert "Encerradas sem resposta" in html
    assert "Você ainda não respondeu nenhuma votação." in html
    assert "Nenhuma votação encerrada sem resposta." in html


def test_indisponibilidade_explica_e_oferece_retorno(client):
    voting, participant, snapshots = create_open_voting(choices_count=1, candidates=2)
    close_voting(voting, "admin")
    _login(client, participant)

    response = client.post(
        reverse("participant:confirm", args=[voting.pk]),
        {"character_ids": [str(snapshots[0].pk)]},
    )
    html = response.content.decode()

    assert response.status_code == 409
    assert "unavailable-state" in html
    assert "A votação não está aberta para receber votos." in html
    assert "Voltar às votações" in html
    assert reverse("participant:home") in html
