# syntax=docker/dockerfile:1.9

ARG PYTHON_VERSION=3.14

# ---------------------------------------------------------------------------
# Build: resolve dependências com uv em um ambiente isolado de /app
# ---------------------------------------------------------------------------
FROM ghcr.io/astral-sh/uv:0.13.5 AS uv

FROM python:${PYTHON_VERSION}-slim AS builder

COPY --from=uv /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
# A validação do Dockerfile do Railway exige cacheKey no `id` do cache do BuildKit.
RUN --mount=type=cache,id=uv-cache-s/uv-cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY . .
RUN --mount=type=cache,id=uv-cache-s/uv-cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Estáticos coletados no build da imagem: o Railway (sem Caddy/volume) os serve
# pelo WhiteNoise. Usa settings base e chave descartável; nunca segredo real.
RUN DJANGO_SETTINGS_MODULE=config.settings.base \
    DJANGO_SECRET_KEY=build-only-not-a-secret-key-0000000000000000000000000000000000000000 \
    STATIC_SERVE_WHITENOISE=True \
    /opt/venv/bin/python manage.py collectstatic --noinput

# ---------------------------------------------------------------------------
# Runtime: imagem mínima, usuário não-root, Gunicorn
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.prod \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app

WORKDIR /app

COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app /app

# A mídia vive em storage externo (bucket no Railway) ou em volume (Compose);
# a imagem não embute media/.
RUN mkdir -p /app/staticfiles /app/media \
    && chown -R app:app /app/staticfiles /app/media

USER app

# Railway injeta PORT; localmente (Compose) o padrão continua 8000.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import os, urllib.request as u; u.urlopen('http://127.0.0.1:%s/health/' % os.environ.get('PORT', '8000'), timeout=3)"

# Um worker por padrão (512 MB no Railway Free); Compose sobrepõe --workers.
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${GUNICORN_WORKERS:-1} --threads 2 --timeout 60 --access-logfile - --error-logfile -"]
