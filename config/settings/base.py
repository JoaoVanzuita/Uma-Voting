"""Configurações compartilhadas por todos os ambientes."""

from pathlib import Path
from urllib.parse import quote

import environ
from django.core.exceptions import ImproperlyConfigured

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
    STATIC_SERVE_WHITENOISE=(bool, False),
    MEDIA_STORAGE_BACKEND=(str, "filesystem"),
    MEDIA_CSP_SOURCE=(str, ""),
    SECURITY_HEADERS_MODE=(str, "proxy"),
    DJANGO_SCHEDULER_MODE=(str, "external"),
    DJANGO_SCHEDULER_TICK_INTERVAL=(int, 60),
    AWS_S3_ENDPOINT_URL=(str, ""),
    AWS_ACCESS_KEY_ID=(str, ""),
    AWS_SECRET_ACCESS_KEY=(str, ""),
    AWS_STORAGE_BUCKET_NAME=(str, ""),
    AWS_S3_REGION_NAME=(str, "auto"),
    AWS_S3_ADDRESSING_STYLE=(str, "virtual"),
    AWS_QUERYSTRING_EXPIRE=(int, 3600),
)

# Valores aceitos pelas variáveis de deploy selecionáveis.
VALID_MEDIA_STORAGE_BACKENDS = {"filesystem", "s3"}
VALID_SECURITY_HEADERS_MODES = {"proxy", "django"}
VALID_SCHEDULER_MODES = {"external", "on_request"}


def _choice(raw_value: str, valid: set[str], variable: str) -> str:
    value = (raw_value or "").strip().lower()
    if value not in valid:
        raise ImproperlyConfigured(
            f"{variable} deve ser um de {sorted(valid)}; recebido {raw_value!r}."
        )
    return value


# Modo de armazenamento de mídia. O filesystem continua sendo o padrão em
# desenvolvimento, testes e Docker Compose; no Railway usa-se o bucket S3.
MEDIA_STORAGE_BACKEND = _choice(
    env("MEDIA_STORAGE_BACKEND"), VALID_MEDIA_STORAGE_BACKENDS, "MEDIA_STORAGE_BACKEND"
)
# Estáticos: False no Compose (Caddy/volume) e True no Railway (WhiteNoise).
STATIC_SERVE_WHITENOISE = env("STATIC_SERVE_WHITENOISE")
# Headers do Caddy replicados no Django quando não há proxy no ambiente.
SECURITY_HEADERS_MODE = _choice(
    env("SECURITY_HEADERS_MODE"), VALID_SECURITY_HEADERS_MODES, "SECURITY_HEADERS_MODE"
)
# Scheduler: processo/container externo (Compose) ou tick sob demanda (Railway).
DJANGO_SCHEDULER_MODE = _choice(
    env("DJANGO_SCHEDULER_MODE"), VALID_SCHEDULER_MODES, "DJANGO_SCHEDULER_MODE"
)
DJANGO_SCHEDULER_TICK_INTERVAL = env("DJANGO_SCHEDULER_TICK_INTERVAL")
if DJANGO_SCHEDULER_TICK_INTERVAL < 0:
    raise ImproperlyConfigured("DJANGO_SCHEDULER_TICK_INTERVAL não pode ser negativo.")

# Origem liberada no CSP para as URLs assinadas do bucket (ex.: https://b.endpoint).
MEDIA_CSP_SOURCE = env("MEDIA_CSP_SOURCE").strip().rstrip("/")

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

# A ordem é a do projeto; entradas condicionais são inseridas na posição certa
# logo abaixo para que Compose/testes continuem com a cadeia original.
_MIDDLEWARE_CONDITIONAL = {
    "whitenoise": "whitenoise.middleware.WhiteNoiseMiddleware",
    "security_headers": "apps.core.security_headers.SecurityHeadersMiddleware",
    "scheduler": "apps.voting.middleware.RequestSchedulerMiddleware",
}


def _with_conditionals(middleware: list[str]) -> list[str]:
    chain = list(middleware)
    if STATIC_SERVE_WHITENOISE:
        chain.insert(1, _MIDDLEWARE_CONDITIONAL["whitenoise"])
    if SECURITY_HEADERS_MODE == "django":
        chain.insert(
            chain.index("apps.core.middleware.RequestIDMiddleware") + 1,
            _MIDDLEWARE_CONDITIONAL["security_headers"],
        )
    if DJANGO_SCHEDULER_MODE == "on_request":
        # Objeto real no fim da cadeia: o tick roda antes da view e depois das
        # sessões, para que a requisição siga com a conexão já aquecida.
        chain.append(_MIDDLEWARE_CONDITIONAL["scheduler"])
    return chain


MIDDLEWARE = _with_conditionals(
    [
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
)

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

# Mídia: filesystem por padrão. Com MEDIA_STORAGE_BACKEND=s3 o acervo vive no
# bucket privado e as URLs são assinadas (Railway Bucket é S3-compatible).
if MEDIA_STORAGE_BACKEND == "s3":
    _MEDIA_STORAGE_OPTIONS = {
        "bucket_name": env("AWS_STORAGE_BUCKET_NAME"),
        "endpoint_url": env("AWS_S3_ENDPOINT_URL"),
        "access_key": env("AWS_ACCESS_KEY_ID"),
        "secret_key": env("AWS_SECRET_ACCESS_KEY"),
        "region_name": env("AWS_S3_REGION_NAME"),
        "addressing_style": env("AWS_S3_ADDRESSING_STYLE"),
        "querystring_auth": True,
        "querystring_expire": env("AWS_QUERYSTRING_EXPIRE"),
        "default_acl": None,
        "file_overwrite": True,
        "signature_version": "s3v4",
        "object_parameters": {"CacheControl": "public, max-age=31536000"},
    }
    _MEDIA_STORAGE = {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": _MEDIA_STORAGE_OPTIONS,
    }
else:
    _MEDIA_STORAGE = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

STORAGES = {
    "default": _MEDIA_STORAGE,
    "staticfiles": (
        {"BACKEND": "apps.core.storage.LenientCompressedManifestStaticFilesStorage"}
        if STATIC_SERVE_WHITENOISE
        else {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}
    ),
}

# WhiteNoise é usado apenas com estáticos coletados no build da imagem.
WHITENOISE_AUTOREFRESH = env("DJANGO_DEBUG")
# Assets com hash de conteúdo podem ficar em cache por um ano (como no Caddy).
WHITENOISE_MAX_AGE = 31_536_000

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
