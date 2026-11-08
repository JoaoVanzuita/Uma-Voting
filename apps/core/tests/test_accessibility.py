"""Auditoria automatizada básica de acessibilidade e responsividade."""

from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse

BASE_DIR = Path(__file__).resolve().parents[3]


@pytest.mark.django_db
def test_pagina_base_tem_idioma_skip_link_e_viewport(client):
    response = client.get(reverse("participant:login"))
    body = response.content.decode()

    assert 'lang="pt-br"' in body
    assert 'name="viewport"' in body
    assert 'href="#conteudo"' in body
    assert "Pular para o conteúdo" in body


@pytest.mark.django_db
def test_mensagens_e_contador_usam_aria_live(client):
    messages_template = (BASE_DIR / "templates/components/messages.html").read_text()
    summary_template = (
        BASE_DIR / "templates/participant/partials/selection_summary.html"
    ).read_text()

    assert 'role="status"' in messages_template
    assert 'aria-live="polite"' in messages_template
    assert 'aria-live="polite"' in summary_template


def test_css_tem_foco_visivel_e_breakpoints_responsivos():
    base_css = (BASE_DIR / "static/css/base.css").read_text()
    components_css = (BASE_DIR / "static/css/components.css").read_text()
    pages_css = (BASE_DIR / "static/css/pages.css").read_text()

    assert ":focus-visible" in base_css
    assert ".skip-link" in base_css
    assert "@media (max-width: 767px)" in base_css
    assert "@media (max-width: 767px)" in components_css
    assert "@media (max-width: 767px)" in pages_css
    assert "prefers-reduced-motion" in base_css


def test_badge_de_estado_nao_depende_apenas_de_cor():
    badge_template = (BASE_DIR / "templates/components/status_badge.html").read_text()

    assert "{{ label }}" in badge_template
    assert "badge--{{ tone }}" in badge_template


@pytest.mark.django_db
def test_navegacao_marca_pagina_atual(client):
    from tests.factories import AdminUserFactory, ParticipantFactory

    participant = ParticipantFactory()
    client.force_login(participant)
    participant_page = client.get(reverse("participant:home"))
    assert 'aria-current="page"' in participant_page.content.decode()

    admin = AdminUserFactory()
    client.force_login(admin)
    admin_page = client.get(reverse("admin:dashboard"))
    assert 'aria-current="page"' in admin_page.content.decode()
