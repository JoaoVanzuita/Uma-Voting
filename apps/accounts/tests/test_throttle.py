"""Testes unitários do throttle de login com DatabaseCache."""

import pytest
from django.core.cache import cache
from django.test import RequestFactory

from apps.accounts.services.throttle import (
    ADMIN_IP_LIMIT,
    ADMIN_USER_LIMIT,
    PARTICIPANT_IP_LIMIT,
    WINDOW_SECONDS,
    check_login_allowed,
    clear_attempts,
    get_client_ip,
    register_attempt,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _limpa_cache(cache_table):
    cache.clear()
    yield
    cache.clear()


def test_limite_administrativo_por_ip_e_username():
    ip = "203.0.113.10"

    for _ in range(ADMIN_USER_LIMIT):
        assert check_login_allowed("admin", ip, "AdminUser").allowed is True
        register_attempt("admin", ip, "AdminUser")

    blocked = check_login_allowed("admin", ip, "AdminUser")

    assert blocked.allowed is False
    assert blocked.retry_after == WINDOW_SECONDS


def test_username_administrativo_e_case_insensitive_no_throttle():
    ip = "203.0.113.11"

    for _ in range(ADMIN_USER_LIMIT):
        register_attempt("admin", ip, "AdminUser")

    assert check_login_allowed("admin", ip, "adminuser").allowed is False


def test_outro_username_nao_e_bloqueado_pelo_limite_por_username():
    ip = "203.0.113.12"

    for _ in range(ADMIN_USER_LIMIT):
        register_attempt("admin", ip, "AdminUser")

    assert check_login_allowed("admin", ip, "OutroAdmin").allowed is True


def test_outro_ip_nao_e_bloqueado_pelo_limite_por_username():
    for _ in range(ADMIN_USER_LIMIT):
        register_attempt("admin", "203.0.113.13", "AdminUser")

    assert check_login_allowed("admin", "203.0.113.14", "AdminUser").allowed is True


def test_limite_administrativo_por_ip_entre_usernames():
    ip = "203.0.113.15"

    for index in range(ADMIN_IP_LIMIT):
        register_attempt("admin", ip, f"Admin{index}")

    blocked = check_login_allowed("admin", ip, "AdminFinal")

    assert blocked.allowed is False
    assert blocked.retry_after == WINDOW_SECONDS


def test_limite_de_participante_por_ip():
    ip = "203.0.113.16"

    for _ in range(PARTICIPANT_IP_LIMIT):
        assert check_login_allowed("participant", ip).allowed is True
        register_attempt("participant", ip)

    blocked = check_login_allowed("participant", ip)

    assert blocked.allowed is False
    assert blocked.retry_after == WINDOW_SECONDS


def test_limpar_falhas_administrativas_libera_o_acesso():
    ip = "203.0.113.17"

    for _ in range(ADMIN_USER_LIMIT):
        register_attempt("admin", ip, "AdminUser")
    assert check_login_allowed("admin", ip, "AdminUser").allowed is False

    clear_attempts("admin", ip, "AdminUser")

    assert check_login_allowed("admin", ip, "AdminUser").allowed is True


def test_requisicao_permitida_nao_tem_retry_after():
    result = check_login_allowed("participant", "203.0.113.18")

    assert result.allowed is True
    assert result.retry_after == 0


def test_get_client_ip_usa_remote_addr_sem_proxy():
    request = RequestFactory().get("/", REMOTE_ADDR="198.51.100.7")

    assert get_client_ip(request) == "198.51.100.7"


def test_get_client_ip_usa_primeiro_ip_do_x_forwarded_for():
    request = RequestFactory().get(
        "/",
        REMOTE_ADDR="10.0.0.2",
        HTTP_X_FORWARDED_FOR="198.51.100.8, 10.0.0.1",
    )

    assert get_client_ip(request) == "198.51.100.8"
