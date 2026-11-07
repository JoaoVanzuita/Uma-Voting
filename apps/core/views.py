"""Views de infraestrutura: healthcheck e páginas de erro."""

from __future__ import annotations

import logging

from django.db import connection
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

logger = logging.getLogger(__name__)


def health(request: HttpRequest) -> JsonResponse:
    """Verifica se a aplicação responde e se o banco está acessível."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:  # noqa: BLE001 - qualquer falha de banco indica indisponibilidade
        logger.exception("Healthcheck falhou ao consultar o banco de dados.")
        response = JsonResponse({"status": "unavailable", "db": "error"}, status=503)
    else:
        response = JsonResponse({"status": "ok", "db": "ok"})

    response["Cache-Control"] = "no-store"
    return response


def _error(request: HttpRequest, template: str, status: int) -> HttpResponse:
    return render(request, template, status=status)


def error_403(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return _error(request, "errors/403.html", 403)


def error_404(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return _error(request, "errors/404.html", 404)


def error_500(request: HttpRequest) -> HttpResponse:
    return _error(request, "errors/500.html", 500)
