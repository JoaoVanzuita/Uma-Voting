"""Middlewares transversais do projeto."""

from __future__ import annotations

import contextvars
import logging
import re
import uuid

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def get_request_id() -> str:
    """Retorna o request ID da requisição corrente (ou ``-`` fora de requisição)."""
    return _request_id.get()


class RequestIDMiddleware:
    """Aceita ou gera um request ID e o devolve no cabeçalho da resposta."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex

        request.request_id = request_id
        # Mantém o contexto ativo após a resposta: o BaseHandler do Django
        # registra 4xx/5xx fora da cadeia de middlewares, e o filtro precisa
        # do ID para correlacionar esse log. A próxima requisição sobrescreve
        # o valor no mesmo contexto.
        _request_id.set(request_id)

        response = self.get_response(request)
        response[REQUEST_ID_HEADER] = request_id
        return response


class RequestIDLogFilter(logging.Filter):
    """Injeta o request ID corrente em cada registro de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True
