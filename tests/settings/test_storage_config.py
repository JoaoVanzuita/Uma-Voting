"""Seleção de armazenamento de mídia e estáticos por ambiente."""

from __future__ import annotations

import importlib
import sys

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.core.files.storage import storages


def settings_from_module(monkeypatch, module_name: str, **env):
    """Importa um módulo de settings novo com variáveis de ambiente aplicadas."""
    base_env = {
        "DJANGO_SETTINGS_MODULE": module_name,
        "DJANGO_SECRET_KEY": "test-secret-key-com-mais-de-50-caracteres-0000000000000000",
        "DJANGO_ALLOWED_HOSTS": "localhost,healthcheck.railway.app",
        "DJANGO_CSRF_TRUSTED_ORIGINS": "https://uma.up.railway.app",
    }
    base_env.update(env)
    for key, value in base_env.items():
        monkeypatch.setenv(key, str(value))

    # Remove os módulos de settings para que o import reavalie o ambiente.
    prefix = "config.settings"
    for name in list(sys.modules):
        if name == prefix or name.startswith(f"{prefix}."):
            del sys.modules[name]
    return importlib.import_module(module_name)


@pytest.fixture
def isolated_storages(monkeypatch):
    def _isolate():
        monkeypatch.setattr(storages, "_storages", {})

    return _isolate


def test_padrao_mantem_filesystem_e_middleware_original(monkeypatch):
    settings = settings_from_module(monkeypatch, "config.settings.base")

    assert settings.MEDIA_STORAGE_BACKEND == "filesystem"
    assert settings.STORAGES["default"]["BACKEND"] == (
        "django.core.files.storage.FileSystemStorage"
    )
    assert settings.STORAGES["staticfiles"]["BACKEND"] == (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
    )
    assert "whitenoise.middleware.WhiteNoiseMiddleware" not in settings.MIDDLEWARE
    assert "apps.voting.middleware.RequestSchedulerMiddleware" not in settings.MIDDLEWARE
    assert "apps.core.security_headers.SecurityHeadersMiddleware" not in settings.MIDDLEWARE
    assert settings.DJANGO_SCHEDULER_MODE == "external"


def test_railway_liga_whitenoise_s3_e_scheduler_sob_demanda(monkeypatch, isolated_storages):
    isolated_storages()
    settings = settings_from_module(
        monkeypatch,
        "config.settings.prod",
        STATIC_SERVE_WHITENOISE="True",
        MEDIA_STORAGE_BACKEND="s3",
        AWS_S3_ENDPOINT_URL="https://t3.storageapi.dev",
        AWS_ACCESS_KEY_ID="chave",
        AWS_SECRET_ACCESS_KEY="segredo",
        AWS_STORAGE_BUCKET_NAME="uma-voting-media-abc123",
        DJANGO_SCHEDULER_MODE="on_request",
        SECURITY_HEADERS_MODE="django",
        DJANGO_LOG_LEVEL="INFO",
    )

    assert settings.STORAGES["default"]["BACKEND"] == "storages.backends.s3.S3Storage"
    options = settings.STORAGES["default"]["OPTIONS"]
    assert options["bucket_name"] == "uma-voting-media-abc123"
    assert options["querystring_auth"] is True
    assert options["default_acl"] is None
    assert options["file_overwrite"] is True

    assert settings.STORAGES["staticfiles"]["BACKEND"] == (
        "apps.core.storage.LenientCompressedManifestStaticFilesStorage"
    )

    # WhiteNoise logo após SecurityMiddleware; headers após RequestID.
    assert settings.MIDDLEWARE[1] == "whitenoise.middleware.WhiteNoiseMiddleware"
    assert settings.MIDDLEWARE[-1] == "apps.voting.middleware.RequestSchedulerMiddleware"


def test_modo_django_instala_headers_apos_request_id(monkeypatch, isolated_storages):
    isolated_storages()
    settings = settings_from_module(
        monkeypatch,
        "config.settings.prod",
        SECURITY_HEADERS_MODE="django",
        DJANGO_LOG_LEVEL="INFO",
    )
    request_id_index = settings.MIDDLEWARE.index("apps.core.middleware.RequestIDMiddleware")

    assert settings.MIDDLEWARE[request_id_index + 1] == (
        "apps.core.security_headers.SecurityHeadersMiddleware"
    )


def test_producao_exige_credenciais_quando_s3(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="AWS_STORAGE_BUCKET_NAME"):
        settings_from_module(monkeypatch, "config.settings.prod", MEDIA_STORAGE_BACKEND="s3")


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("MEDIA_STORAGE_BACKEND", "gcs"),
        ("SECURITY_HEADERS_MODE", "caddy"),
        ("DJANGO_SCHEDULER_MODE", "always"),
    ],
)
def test_valores_invalidos_falham_cedo(monkeypatch, variable, value):
    with pytest.raises(ImproperlyConfigured, match=variable):
        settings_from_module(monkeypatch, "config.settings.base", **{variable: value})


def test_white_noise_nao_e_ligado_em_dev(monkeypatch):
    settings = settings_from_module(
        monkeypatch, "config.settings.dev", STATIC_SERVE_WHITENOISE="True"
    )

    # dev.py desliga o WhiteNoise no middleware: runserver serve os estáticos
    # com auto-reload e sem depender de manifest coletado.
    assert "whitenoise.middleware.WhiteNoiseMiddleware" not in settings.MIDDLEWARE
