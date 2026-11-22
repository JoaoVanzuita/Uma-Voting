"""Headers de segurança replicados do Caddy quando não há proxy."""

from __future__ import annotations

import pytest
from django.http import HttpResponse
from django.test import Client, override_settings

from apps.core.security_headers import (
    PlatformHealthcheckMiddleware,
    SecurityHeadersMiddleware,
    content_security_policy,
)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "apps.core.security_headers.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


def fake_request(path: str = "/"):
    return type("Request", (), {"method": "GET", "path": path})()


def test_csp_mantem_politica_do_caddy_sem_bucket():
    policy = content_security_policy()

    assert "default-src 'self'" in policy
    assert "img-src 'self' data:" in policy
    assert "script-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "form-action 'self'" in policy


@override_settings(MEDIA_CSP_SOURCE="https://uma-voting-media-abc.t3.storageapi.dev")
def test_csp_libera_apenas_o_host_do_bucket_em_img_src():
    policy = content_security_policy()

    assert "img-src 'self' data: https://uma-voting-media-abc.t3.storageapi.dev;" in policy
    assert policy.count("https://") == 1


def test_headers_replicam_o_caddyfile():
    middleware = SecurityHeadersMiddleware(lambda request: HttpResponse())

    response = middleware(fake_request())

    assert response["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"
    assert response["Cross-Origin-Resource-Policy"] == "same-origin"
    assert response["Referrer-Policy"] == "same-origin"
    assert response["X-Frame-Options"] == "DENY"
    assert response["Content-Security-Policy"].startswith("default-src 'self'")


def test_headers_nao_sobrescrevem_valores_ja_definidos():
    response = HttpResponse()
    response["Content-Security-Policy"] = "default-src 'none'"
    middleware = SecurityHeadersMiddleware(lambda request: response)

    middleware(fake_request())

    assert response["Content-Security-Policy"] == "default-src 'none'"


@pytest.mark.django_db
def test_health_recebe_csp_quando_modo_django(client: Client):
    with override_settings(MIDDLEWARE=MIDDLEWARE, SECURITY_HEADERS_MODE="django"):
        response = client.get("/health/")

    assert response.status_code == 200
    assert "img-src 'self' data:" in response["Content-Security-Policy"]


@override_settings(ALLOWED_HOSTS=["healthcheck.railway.app", "uma.up.railway.app"])
def test_healthcheck_da_plataforma_e_tratado_como_https():
    middleware = PlatformHealthcheckMiddleware(
        lambda request: request.META["HTTP_X_FORWARDED_PROTO"]
    )

    protocol = middleware(_request(path="/health/", host="healthcheck.railway.app"))

    assert protocol == "https"


@override_settings(ALLOWED_HOSTS=["uma.up.railway.app"])
def test_apenas_healthcheck_da_plataforma_e_isento():
    middleware = PlatformHealthcheckMiddleware(
        lambda request: request.META.get("HTTP_X_FORWARDED_PROTO")
    )

    assert middleware(_request(path="/health/", host="uma.up.railway.app")) is None
    assert middleware(_request(path="/entrar/", host="uma.up.railway.app")) is None


@override_settings(ALLOWED_HOSTS=["uma.up.railway.app"])
def test_requisicao_https_nao_e_alterada():
    middleware = PlatformHealthcheckMiddleware(
        lambda request: request.META.get("HTTP_X_FORWARDED_PROTO")
    )

    assert (
        middleware(_request(path="/health/", host="uma.up.railway.app", proto="https")) == "https"
    )


def _request(path: str = "/", host: str = "testserver", proto: str | None = None):
    from django.test import RequestFactory

    request = RequestFactory().get(path, headers={"host": host})
    if proto:
        request.META["HTTP_X_FORWARDED_PROTO"] = proto
    return request
