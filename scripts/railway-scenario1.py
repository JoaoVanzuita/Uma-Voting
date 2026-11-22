"""Cenário 1 do plano de produção: votação manual ponta a ponta (via HTTP).

Executa o fluxo **pela interface HTTP** (não pelo ORM): login admin, criação de
rascunhos `TESTE manual …`, abertura, login do participante, seleção, revisão,
confirmação, encerramento e resultado. Cada usuário tem cookie jar próprio e o
CSRF é extraído de cada formulário.

    ADMIN_PASSWORD=... python3 scripts/railway-scenario1.py --base-url https://...
    ADMIN_PASSWORD=... python3 scripts/railway-scenario1.py --base-url https://... --confirm

Sem `--confirm` o script apenas cria/abre e mostra o resumo (útil para revisar).
Nada é apagado. Os rascunhos ficam para `purge_test_votings --prefix "TESTE "`.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import date

CSRF_RE = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')
ID_RE = re.compile(r"/admin/votacoes/(\d+)/")


def fail(message: str) -> None:
    print(f"FALHA: {message}")
    sys.exit(1)


@dataclass
class Browser:
    base_url: str
    cookies: http.cookiejar.CookieJar = field(default_factory=http.cookiejar.CookieJar)

    def __post_init__(self) -> None:
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def get(self, path: str) -> tuple[int, str, str]:
        try:
            with self.opener.open(self.base_url + path, timeout=60) as response:
                return response.status, response.read().decode("utf-8", "replace"), response.url
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace"), exc.url

    def post(self, path: str, data, referer: str) -> tuple[int, str, str]:
        body = urllib.parse.urlencode(data, doseq=True).encode()
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method="POST",
            headers={"Referer": self.base_url + referer},
        )
        try:
            with self.opener.open(request, timeout=180) as response:
                return response.status, response.read().decode("utf-8", "replace"), response.url
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace"), exc.url

    @staticmethod
    def csrf(html: str) -> str:
        match = CSRF_RE.search(html)
        if not match:
            raise RuntimeError("CSRF token não encontrado.")
        return match.group(1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("APP_BASE_URL", ""))
    parser.add_argument("--admin-username", default=os.environ.get("ADMIN_USERNAME", "Jota"))
    parser.add_argument("--participant", default=os.environ.get("PARTICIPANT", "teste_ana"))
    parser.add_argument("--cutoff", default=date.today().isoformat())
    parser.add_argument("--confirm", action="store_true", help="Executa o voto e o encerramento.")
    args = parser.parse_args()

    if not args.base_url:
        fail("informe --base-url")
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        fail("defina ADMIN_PASSWORD")

    base = args.base_url.rstrip("/")
    admin = Browser(base)

    print("1) login do administrador")
    status, html, _ = admin.get("/admin/entrar/")
    status, html, url = admin.post(
        "/admin/entrar/",
        {
            "csrfmiddlewaretoken": Browser.csrf(html),
            "username": args.admin_username,
            "password": password,
        },
        "/admin/entrar/",
    )
    if status != 200 or "/admin/" not in url:
        fail(f"login admin (status {status}, url {url})")
    print("   ok:", url)

    today = date.today().isoformat()
    created: list[tuple[int, str]] = []
    for index in (1, 2):
        title = f"TESTE manual {today} #{index}"
        status, html, _ = admin.get("/admin/votacoes/nova/")
        if status != 200:
            fail(f"formulário de criação retornou {status}")
        fields = {
            "csrfmiddlewaretoken": Browser.csrf(html),
            "title": title,
            "description": "Votação de teste do plano de produção (automatizada).",
            "choices_count": "1",
            "catalog_cutoff_date": args.cutoff,
            "open_mode": "manual",
            "close_mode": "manual",
            "opens_at": "",
            "closes_at": "",
            "action": "draft",
        }
        status, html, url = admin.post("/admin/votacoes/nova/", fields, "/admin/votacoes/nova/")
        match = ID_RE.search(url)
        if status != 200 or not match:
            fail(f"criação falhou (status {status}, url {url})")
        voting_id = int(match.group(1))
        created.append((voting_id, title))
        print(f"2.{index}) rascunho criado: id={voting_id} '{title}'")

    voting_id, _ = created[0]
    detail = f"/admin/votacoes/{voting_id}/"

    print(f"3) abrindo manualmente a votação {voting_id}")
    status, html, url = admin.post(
        f"{detail}abrir/", {"csrfmiddlewaretoken": Browser.csrf(admin.get(detail)[1])}, detail
    )
    if status != 200:
        fail(f"abertura retornou {status}")
    status, html, _ = admin.get(detail)
    opened = "encerrar/" in html and "cancelar/" in html and ">Aberta<" in re.sub(r"\s+", "", html)
    print(f"   status 'Aberta' no detalhe: {opened}")
    if not opened:
        fail("a votação não aparenta estar aberta no detalhe")

    base = args.base_url.rstrip("/")
    participant = Browser(base)
    print(f"4) participante {args.participant}")
    status, html, _ = participant.get("/entrar/")
    status, html, url = participant.post(
        "/entrar/",
        {"csrfmiddlewaretoken": Browser.csrf(html), "username": args.participant},
        "/entrar/",
    )
    if status != 200:
        fail(f"login do participante ({status})")

    status, html, url = participant.get(f"/votacoes/{voting_id}/")
    if status != 200:
        fail(f"página da votação retornou {status} para o participante")
    snapshots = sorted(
        {int(value) for value in re.findall(r'name="character_ids"\s+value="(\d+)"', html)}
    )
    if not snapshots:
        fail("nenhuma personagem disponível na página da votação")
    chosen = snapshots[0]
    print(f"   personagem escolhida: snapshot {chosen} (de {len(snapshots)} disponíveis)")

    review = f"/votacoes/{voting_id}/revisar/"
    status, html, url = participant.post(
        review,
        {"csrfmiddlewaretoken": Browser.csrf(html), "character_ids": str(chosen)},
        f"/votacoes/{voting_id}/",
    )
    if status != 200:
        fail(f"revisão retornou {status}")
    print("   revisão ok")

    if args.confirm:
        confirm = f"/votacoes/{voting_id}/confirmar/"
        status, html, url = participant.post(
            confirm,
            {"csrfmiddlewaretoken": Browser.csrf(html), "character_ids": str(chosen)},
            review,
        )
        print(f"5) confirmação: status {status} -> {url}")
        status, html, url = participant.get(f"/votacoes/{voting_id}/cedula/")
        print(f"   cédula: status {status}")
        status, html, url = admin.get(f"{detail}resultados/")
        confirmation = "1 cédula" in html or "100" in html
        print(f"6) resultados do admin: status {status} (participação registrada: {confirmation})")

    print("7) encerrando" if args.confirm else "7) encerramento pulado (use --confirm)")
    if args.confirm:
        status, html, url = admin.post(
            f"{detail}encerrar/",
            {"csrfmiddlewaretoken": Browser.csrf(admin.get(detail)[1])},
            detail,
        )
        print(f"   encerrar: status {status} -> {url}")
        status, html, url = admin.get(detail)
        closed = "encerrar/" not in html and "cancelar/" in html
        print(f"   detalhe após encerrar (sem ações de encerramento): {closed}")

    print("\nResumo:")
    for item_id, title in created:
        print(f"  {item_id}: {title}")


if __name__ == "__main__":
    main()
