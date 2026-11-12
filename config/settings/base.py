"""Configurações compartilhadas por todos os ambientes."""

from pathlib import Path
from urllib.parse import quote

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, "insecure-dev-key-change-me"),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_CSRF_TRUSTED_ORIGINS=(list, []),
    DJANGO_TIME_ZONE=(str, "America/Sao_Paulo"),
    DJANGO_LOG_LEVEL=(str, "INFO"),
    DJANGO_SECURE_SSL_REDIRECT=(bool, False),
    DJANGO_SESSION_COOKIE_SECURE=(bool, False),
    DJANGO_CSRF_COOKIE_SECURE=(bool, False),
    DJANGO_DB_CONN_MAX_AGE=(int, 60),
    DJANGO_SESSION_COOKIE_AGE=(int, 43200),
    EXTERNAL_IMPORT_ENABLED=(bool, False),
    EXTERNAL_IMPORT_HTTP_TIMEOUT=(int, 15),
    EXTERNAL_IMPORT_MAX_IMAGE_BYTES=(int, 5 * 1024 * 1024),
    EXTERNAL_IMPORT_CONCURRENCY=(int, 4),
    EXTERNAL_IMPORT_STALE_SECONDS=(int, 600),
)

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS")

# ---------------------------------------------------------------------------
# Aplicações
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.accounts",
    "apps.catalog",
    "apps.voting",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.middleware.AdminModeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.admin_mode",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Banco de dados
# ---------------------------------------------------------------------------
# As credenciais vivem apenas nas variáveis POSTGRES_* (as mesmas usadas pelo
# container do Postgres no Compose). DATABASE_URL é opcional e, se definida,
# tem precedência (útil em CI e plataformas que entregam a URL pronta).
POSTGRES_DB = env("POSTGRES_DB", default="uma_voting")
POSTGRES_USER = env("POSTGRES_USER", default="uma_voting")
POSTGRES_PASSWORD = env("POSTGRES_PASSWORD", default="uma_voting")
POSTGRES_HOST = env("POSTGRES_HOST", default="localhost")
POSTGRES_PORT = env("POSTGRES_PORT", default="5432")

DATABASES = {
    "default": env.db_url(
        "DATABASE_URL",
        default=(
            f"postgres://{quote(POSTGRES_USER, safe='')}:{quote(POSTGRES_PASSWORD, safe='')}"
            f"@{POSTGRES_HOST}:{POSTGRES_PORT}/{quote(POSTGRES_DB, safe='')}"
        ),
    )
}
DATABASES["default"]["CONN_MAX_AGE"] = env("DJANGO_DB_CONN_MAX_AGE")
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LOGIN_URL = "/entrar/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/entrar/"

# ---------------------------------------------------------------------------
# Internacionalização e fuso horário
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "pt-br"
TIME_ZONE = env("DJANGO_TIME_ZONE")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Arquivos estáticos e mídia
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# ---------------------------------------------------------------------------
# Sessão, CSRF e segurança base
# ---------------------------------------------------------------------------
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = "uma_voting_sessionid"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = env("DJANGO_SESSION_COOKIE_SECURE")
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = env("DJANGO_SESSION_COOKIE_AGE")

CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = env("DJANGO_CSRF_COOKIE_SECURE")
# O HTMX envia o token no cabeçalho X-CSRFToken; o cookie precisa ser legível.
CSRF_COOKIE_HTTPONLY = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# Entradas de formulário e uploads ficam limitadas (contratos de importação: 5 MB).
DATA_UPLOAD_MAX_MEMORY_SIZE = 6 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# ---------------------------------------------------------------------------
# Importação externa de catálogo e imagens
# ---------------------------------------------------------------------------
# A importação externa é opcional e desligada por padrão (kill switch).
EXTERNAL_IMPORT_ENABLED = env("EXTERNAL_IMPORT_ENABLED")
# Timeout de conexão/leitura por requisição ao conector externo.
EXTERNAL_IMPORT_HTTP_TIMEOUT = env("EXTERNAL_IMPORT_HTTP_TIMEOUT")
# Limite por resposta de imagem; acima disso a imagem é rejeitada.
EXTERNAL_IMPORT_MAX_IMAGE_BYTES = env("EXTERNAL_IMPORT_MAX_IMAGE_BYTES")
# Downloads simultâneos na fase de imagens.
EXTERNAL_IMPORT_CONCURRENCY = env("EXTERNAL_IMPORT_CONCURRENCY")
# Execução `running` sem heartbeat por esse tempo é marcada como falha.
EXTERNAL_IMPORT_STALE_SECONDS = env("EXTERNAL_IMPORT_STALE_SECONDS")

# ---------------------------------------------------------------------------
# Cache compartilhado entre workers (throttle de login)
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "uma_voting_cache",
    }
}

# ---------------------------------------------------------------------------
# Logging (sem dados sensíveis; request ID por requisição)
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "apps.core.middleware.RequestIDLogFilter"},
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {name} [request_id={request_id}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["request_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": env("DJANGO_LOG_LEVEL"),
    },
    "loggers": {
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Transições do worker de importação externa. Campos estruturados
        # (job_id, source, phase, status) sem credenciais ou dados pessoais.
        "apps.catalog.imports": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
