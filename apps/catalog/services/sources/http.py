"""Cliente HTTP allowlisted usado apenas pelos conectores externos.

Regras de segurança (contracts/source-adapters.md §3):

- somente HTTPS;
- host precisa estar na allowlist do conector;
- resolução DNS validada contra loopback, faixas privadas, link-local,
  multicast e reservadas;
- redirecionamentos limitados e revalidados;
- timeout, limite de bytes e retry com backoff para 429/5xx/timeout;
- cache em memória por instância (uma execução do worker).
"""

from __future__ import annotations

import ipaddress
import json
import socket
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from typing import Any
from urllib.parse import urljoin, urlsplit

from apps.catalog.services.sources.base import SourceDataError, SourceHTTPError

MAX_REDIRECTS = 3
DEFAULT_MAX_BYTES = 5 * 1024 * 1024
READ_CHUNK = 64 * 1024
RETRY_STATUSES = {429, 500, 502, 503, 504}


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Impede que o urllib siga redirecionamentos sem revalidação."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


class HttpClient:
    """Cliente somente leitura, com allowlist e limites por resposta."""

    def __init__(
        self,
        *,
        allowed_hosts: tuple[str, ...],
        timeout: float = 15,
        max_bytes: int = DEFAULT_MAX_BYTES,
        user_agent: str,
        retries: int = 3,
    ) -> None:
        self.allowed_hosts = tuple(host.casefold() for host in allowed_hosts)
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.user_agent = user_agent
        self.retries = max(1, retries)
        self._cache: dict[str, bytes] = {}
        self._opener = urllib.request.build_opener(_NoRedirectHandler)
        self._sleep = time.sleep

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------
    def get_bytes(self, url: str, *, max_bytes: int | None = None) -> bytes:
        limit = self.max_bytes if max_bytes is None else max_bytes
        cache_key = f"{url}|{limit}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        data = self._fetch(url, limit=limit)
        self._cache[cache_key] = data
        return data

    def get_text(self, url: str, *, max_bytes: int | None = None) -> str:
        data = self.get_bytes(url, max_bytes=max_bytes)
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise SourceDataError(f"Resposta não está em UTF-8: {url}") from exc

    def get_json(self, url: str, *, max_bytes: int | None = None) -> Any:
        text = self.get_text(url, max_bytes=max_bytes)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SourceDataError(f"Resposta não é JSON válido: {url}") from exc

    # ------------------------------------------------------------------
    # Interno
    # ------------------------------------------------------------------
    def _validate_url(self, url: str) -> str:
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise SourceHTTPError("Somente HTTPS é permitido.", url=url)
        host = (parts.hostname or "").casefold()
        if not host:
            raise SourceHTTPError("URL sem host.", url=url)
        if host not in self.allowed_hosts:
            raise SourceHTTPError(
                f"Host não autorizado para importação: {host}.",
                url=url,
            )
        if parts.port not in (None, 443):
            raise SourceHTTPError("Porta não autorizada.", url=url)
        self._validate_resolution(host, url)
        return url

    def _validate_resolution(self, host: str, url: str) -> None:
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(host, 443)}
        except socket.gaierror as exc:
            raise SourceHTTPError(f"Falha ao resolver o host {host}.", url=url) from exc

        for raw in addresses:
            try:
                address = ipaddress.ip_address(raw)
            except ValueError as exc:
                raise SourceHTTPError("Endereço IP inválido na resolução.", url=url) from exc
            if (
                address.is_private
                or address.is_loopback
                or address.is_link_local
                or address.is_multicast
                or address.is_reserved
                or address.is_unspecified
            ):
                raise SourceHTTPError(
                    f"Destino de rede não permitido: {raw}.",
                    url=url,
                )

    def _open(self, request: urllib.request.Request):
        return self._opener.open(request, timeout=self.timeout)

    def _fetch(self, url: str, *, limit: int) -> bytes:
        current = url
        for _hop in range(MAX_REDIRECTS + 1):
            self._validate_url(current)
            response = self._request_with_retry(current)
            status = getattr(response, "status", None) or response.getcode()
            if status in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                response.close()
                if not location:
                    raise SourceHTTPError(
                        "Redirecionamento sem destino.",
                        status=status,
                        url=current,
                    )
                current = urljoin(current, location)
                continue
            if status >= 400:
                response.close()
                raise SourceHTTPError(
                    f"Resposta HTTP {status}.",
                    status=status,
                    url=current,
                )
            try:
                return self._read_limited(response, limit=limit, url=current)
            finally:
                response.close()
        raise SourceHTTPError(
            f"Excesso de redirecionamentos (máximo {MAX_REDIRECTS}).",
            url=url,
        )

    def _request_with_retry(self, url: str):
        last_error: Exception | None = None
        for attempt in range(self.retries):
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": self.user_agent,
                    "Accept": "application/json, text/html;q=0.9, image/*;q=0.8",
                },
            )
            try:
                response = self._open(request)
            except urllib.error.HTTPError as exc:
                if exc.code in RETRY_STATUSES and attempt + 1 < self.retries:
                    last_error = exc
                    self._sleep(min(2**attempt, 8))
                    continue
                raise SourceHTTPError(
                    f"Resposta HTTP {exc.code}.",
                    status=exc.code,
                    url=url,
                ) from exc
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                if attempt + 1 < self.retries:
                    last_error = exc
                    self._sleep(min(2**attempt, 8))
                    continue
                raise SourceHTTPError(
                    f"Falha de rede ao acessar {url}: {exc}.",
                    url=url,
                ) from exc

            status = getattr(response, "status", None) or response.getcode()
            if status in RETRY_STATUSES and attempt + 1 < self.retries:
                response.close()
                last_error = SourceHTTPError(
                    f"Resposta HTTP {status}.",
                    status=status,
                    url=url,
                )
                self._sleep(min(2**attempt, 8))
                continue
            return response
        raise SourceHTTPError(f"Falha de rede ao acessar {url}: {last_error}.", url=url)

    def _read_limited(self, response, *, limit: int, url: str) -> bytes:
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = response.read(READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                raise SourceHTTPError(
                    f"Resposta excede o limite de {limit} bytes.",
                    url=url,
                )
            chunks.append(chunk)
        return b"".join(chunks)


def header_value(headers: Mapping[str, str], name: str) -> str:
    """Lê um cabeçalho sem depender da capitalização usada pelo servidor."""
    lowered = name.casefold()
    for key, value in headers.items():
        if key.casefold() == lowered:
            return value
    return ""
