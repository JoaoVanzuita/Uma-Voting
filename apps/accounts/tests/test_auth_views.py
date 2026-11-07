"""Testes de integração de login, logout, sessão e alternância de modo."""

import pytest
from django.conf import settings
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from tests.factories import (
    DEFAULT_ADMIN_PASSWORD,
    AdminUserFactory,
    ParticipantFactory,
    UserFactory,
)

from apps.core.middleware import ADMIN_MODE_SESSION_KEY

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _limpa_cache(cache_table):
    cache.clear()
    yield
    cache.clear()


# ---------------------------------------------------------------------------
# Login administrativo
# ---------------------------------------------------------------------------


def test_admin_entra_com_username_e_senha(client):
    admin = AdminUserFactory(username="AdminUser")

    response = client.post(
        reverse("admin:login"),
        {"username": "adminuser", "password": DEFAULT_ADMIN_PASSWORD},
    )

    assert response.status_code == 302
    assert response.url == reverse("admin:dashboard")
    assert client.session["_auth_user_id"] == str(admin.pk)


def test_admin_senha_incorreta_usa_mensagem_generica(client):
    AdminUserFactory(username="AdminUser")

    response = client.post(
        reverse("admin:login"),
        {"username": "AdminUser", "password": "senha-errada"},
    )

    assert response.status_code == 200
    assert "Username ou senha inválidos." in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_nao_admin_nao_entra_pela_area_administrativa(client):
    ParticipantFactory(username="Participante")

    response = client.post(
        reverse("admin:login"),
        {"username": "Participante", "password": "qualquer-coisa"},
    )

    assert response.status_code == 200
    assert "Username ou senha inválidos." in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_admin_autenticado_que_visita_login_vai_para_dashboard(client):
    admin = AdminUserFactory()
    client.force_login(admin)

    response = client.get(reverse("admin:login"))

    assert response.status_code == 302
    assert response.url == reverse("admin:dashboard")


# ---------------------------------------------------------------------------
# Login de participante
# ---------------------------------------------------------------------------


def test_participante_entra_somente_com_username(client):
    participant = ParticipantFactory(username="SpecialWeek")

    response = client.post(
        reverse("participant:login"),
        {"username": "specialweek"},
    )

    assert response.status_code == 302
    assert response.url == reverse("participant:home")
    assert client.session["_auth_user_id"] == str(participant.pk)

    participant.refresh_from_db()
    assert participant.last_login is not None


@pytest.mark.parametrize("username", ["NaoExiste", "Inativo"])
def test_participante_inexistente_ou_inativo_recebe_mensagem_generica(client, username):
    if username == "Inativo":
        UserFactory(username="Inativo", is_active=False)

    response = client.post(reverse("participant:login"), {"username": username})

    assert response.status_code == 200
    assert "Não foi possível entrar com esse username." in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_username_administrativo_e_rejeitado_no_fluxo_de_participante(client):
    AdminUserFactory(username="AdminUser")

    response = client.post(
        reverse("participant:login"),
        {"username": "AdminUser"},
    )

    assert response.status_code == 200
    assert "Não foi possível entrar com esse username." in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_pagina_de_login_exibe_aviso_de_limitacao_do_username(client):
    response = client.get(reverse("participant:login"))

    assert response.status_code == 200
    assert (
        "Este acesso identifica apenas o username; não comprova sua identidade."
        in response.content.decode()
    )


def test_participante_autenticado_que_visita_login_vai_para_home(client):
    participant = ParticipantFactory()
    client.force_login(participant)

    response = client.get(reverse("participant:login"))

    assert response.status_code == 302
    assert response.url == reverse("participant:home")


# ---------------------------------------------------------------------------
# Logout e sessão
# ---------------------------------------------------------------------------


def test_logout_de_participante_encerra_sessao(client):
    participant = ParticipantFactory()
    client.force_login(participant)

    response = client.post(reverse("participant:logout"))

    assert response.status_code == 302
    assert response.url == reverse("participant:login")
    assert "_auth_user_id" not in client.session


def test_logout_exige_post(client):
    participant = ParticipantFactory()
    client.force_login(participant)

    response = client.get(reverse("participant:logout"))

    assert response.status_code == 405


def test_logout_administrativo_encerra_sessao(client):
    admin = AdminUserFactory()
    client.force_login(admin)

    response = client.post(reverse("admin:logout"))

    assert response.status_code == 302
    assert response.url == reverse("admin:login")
    assert "_auth_user_id" not in client.session


def test_cookie_de_sessao_expira_ao_fechar_navegador(client):
    ParticipantFactory(username="SpecialWeek")

    response = client.post(
        reverse("participant:login"),
        {"username": "SpecialWeek"},
    )

    cookie = response.cookies[settings.SESSION_COOKIE_NAME]
    assert cookie["expires"] in ("", None)
    assert cookie["max-age"] in ("", None)


# ---------------------------------------------------------------------------
# CSRF e autorização
# ---------------------------------------------------------------------------


def test_login_sem_csrf_e_rejeitado():
    csrf_client = Client(enforce_csrf_checks=True)
    ParticipantFactory(username="SpecialWeek")

    response = csrf_client.post(
        reverse("participant:login"),
        {"username": "SpecialWeek"},
    )

    assert response.status_code == 403


def test_login_com_csrf_valido_funciona():
    csrf_client = Client(enforce_csrf_checks=True)
    ParticipantFactory(username="SpecialWeek")

    page = csrf_client.get(reverse("participant:login"))
    token = page.cookies["csrftoken"].value

    response = csrf_client.post(
        reverse("participant:login"),
        {"username": "SpecialWeek", "csrfmiddlewaretoken": token},
        headers={"X-CSRFToken": token},
    )

    assert response.status_code == 302
    assert response.url == reverse("participant:home")


def test_area_protegida_redireciona_visitante_para_login(client):
    response = client.get(reverse("participant:home"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("participant:login"))


def test_area_administrativa_redireciona_visitante_para_login_admin(client):
    response = client.get(reverse("admin:dashboard"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("admin:login"))


def test_participante_nao_acessa_area_administrativa(client):
    participant = ParticipantFactory()
    client.force_login(participant)

    response = client.get(reverse("admin:dashboard"))

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Alternância de modo
# ---------------------------------------------------------------------------


def test_admin_alterna_para_modo_participante(client):
    admin = AdminUserFactory()
    client.force_login(admin)

    response = client.post(reverse("admin:participant_mode"))

    assert response.status_code == 302
    assert response.url == reverse("participant:home")
    assert client.session[ADMIN_MODE_SESSION_KEY] is True

    home = client.get(reverse("participant:home"))
    assert home.status_code == 200
    assert "Modo participante ativo." in home.content.decode()


def test_admin_retorna_ao_modo_administrativo(client):
    admin = AdminUserFactory()
    client.force_login(admin)
    client.post(reverse("admin:participant_mode"))

    response = client.post(reverse("participant:admin_mode"))

    assert response.status_code == 302
    assert response.url == reverse("admin:dashboard")
    assert client.session[ADMIN_MODE_SESSION_KEY] is False


def test_participante_nao_pode_alternar_modo(client):
    participant = ParticipantFactory()
    client.force_login(participant)

    response = client.post(reverse("admin:participant_mode"))

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Throttle nos fluxos reais
# ---------------------------------------------------------------------------


def test_throttle_bloqueia_login_administrativo_apos_cinco_falhas(client):
    AdminUserFactory(username="AdminUser")

    for _ in range(5):
        client.post(
            reverse("admin:login"),
            {"username": "AdminUser", "password": "senha-errada"},
        )

    response = client.post(
        reverse("admin:login"),
        {"username": "AdminUser", "password": DEFAULT_ADMIN_PASSWORD},
    )

    assert response.status_code == 429
    assert "_auth_user_id" not in client.session


def test_throttle_bloqueia_participante_apos_vinte_tentativas(client):
    for _ in range(20):
        response = client.post(reverse("participant:login"), {"username": "Fantasma"})
        assert response.status_code == 200

    response = client.post(reverse("participant:login"), {"username": "Fantasma"})

    assert response.status_code == 429
