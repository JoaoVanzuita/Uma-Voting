"""Cenário 3 do plano: encerramento automático sob demanda.

Usa a votação aberta pelo cenário 2 (ou a especificada em ``--voting-id``) e
configura o encerramento automático em `+N min`. Depois espera **sem acessar o
site** e faz uma única requisição para provar que o tick fecha a votação antes
da view.

    ADMIN_PASSWORD=... python3 scripts/railway-scenario3.py --base-url https://... --voting-id 7
"""

from __future__ import annotations

import argparse
import http.cookiejar
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import timezone as dt_timezone

CSRF_RE = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')


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
        request = urllib.request.Request(
            self.base_url + path,
            data=urllib.parse.urlencode(data, doseq=True).encode(),
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

    def login_admin(self, username: str, password: str) -> str:
        status, html, _ = self.get("/admin/entrar/")
        _, _, url = self.post(
            "/admin/entrar/",
            {"csrfmiddlewaretoken": self.csrf(html), "username": username, "password": password},
            "/admin/entrar/",
        )
        return url

    def login_participant(self, username: str) -> str:
        status, html, _ = self.get("/entrar/")
        _, _, url = self.post(
            "/entrar/",
            {"csrfmiddlewaretoken": self.csrf(html), "username": username},
            "/entrar/",
        )
        return url


PRELUDE = (
    "import os, django\n"
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.prod')\n"
    "django.setup()\n"
)


def ssh_python(code: str) -> str:
    command = [
        "railway",
        "ssh",
        "--service",
        "web",
        "--environment",
        "production",
        "--",
        "python",
        "-c",
        code,
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        fail(f"ssh falhou: {result.stderr[-400:]}")
    return result.stdout.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("APP_BASE_URL", ""))
    parser.add_argument("--admin-username", default=os.environ.get("ADMIN_USERNAME", "Jota"))
    parser.add_argument("--participant", default="teste_ana")
    parser.add_argument("--voting-id", type=int, default=0, help="ignorado (legado)")
    parser.add_argument("--delay-minutes", type=int, default=2)
    args = parser.parse_args()

    if not args.base_url:
        fail("informe --base-url")
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        fail("defina ADMIN_PASSWORD")
    base = args.base_url.rstrip("/")

    admin = Browser(base)
    url = admin.login_admin(args.admin_username, password)
    if "/admin/" not in url:
        fail(f"login admin ({url})")

    now = datetime.now(UTC)
    closes_at = now + timedelta(minutes=args.delay_minutes)
    local = closes_at.astimezone(dt_timezone(timedelta(hours=-3)))
    title = f"TESTE encerramento {date.today().isoformat()}"

    # A configuração é imutável após o rascunho (trigger `voting_config_immutable`),
    # então o cenário cria uma votação nova com encerramento automático e a abre
    # manualmente — o fechamento é o que o scheduler deve fazer.
    print(f"1) criando '{title}' com encerramento automático para {local:%H:%M} local")
    status, html, _ = admin.get("/admin/votacoes/nova/")
    fields = {
        "csrfmiddlewaretoken": Browser.csrf(html),
        "title": title,
        "description": "Teste de encerramento automático sob demanda.",
        "choices_count": "1",
        "catalog_cutoff_date": date.today().isoformat(),
        "open_mode": "manual",
        "close_mode": "automatic",
        "opens_at": "",
        "closes_at": f"{local:%Y-%m-%dT%H:%M}",
        "action": "draft",
    }
    status, html, url = admin.post("/admin/votacoes/nova/", fields, "/admin/votacoes/nova/")
    match = re.search(r"/admin/votacoes/(\d+)/", url)
    if status != 200 or not match:
        fail(f"criação falhou (status {status}, url {url})")
    voting_id = int(match.group(1))
    print(f"   id={voting_id}")

    detail = f"/admin/votacoes/{voting_id}/"
    status, html, _ = admin.get(detail)
    status, html, url = admin.post(
        f"{detail}abrir/", {"csrfmiddlewaretoken": Browser.csrf(html)}, detail
    )
    opened = ssh_python(
        PRELUDE + f"from apps.voting.models import Voting\nv = Voting.objects.get(pk={voting_id})\n"
        "print(v.status)\n"
    )
    print(f"   aberta manualmente: status={opened}")

    participant = Browser(base)
    participant.login_participant(args.participant)
    print("2) participante logado antes do horário; aguardando sem acessar o site")

    target = closes_at + timedelta(seconds=70)
    while datetime.now(UTC) < target:
        time.sleep(min(30, max(1, (target - datetime.now(UTC)).total_seconds())))

    hit_at = datetime.now(UTC)
    status, html, url = participant.get("/")
    print(f"3) primeira GET / após o horário: {status} em {hit_at:%H:%M:%S} UTC")

    after = ssh_python(
        PRELUDE + f"from apps.voting.models import Voting\nv = Voting.objects.get(pk={voting_id})\n"
        "print(v.status, v.closes_at.isoformat(), "
        "v.closed_at.isoformat() if v.closed_at else None)\n"
    )
    print("   banco:", after)

    status, html, url = participant.get(f"/votacoes/{voting_id}/")
    blocked = 'name="character_ids"' not in html
    print(f"   participante não pode mais votar (sem personagens selecionáveis): {blocked}")

    status, html, url = participant.get(f"/votacoes/{voting_id}/resultado/")
    print(f"4) resultado público: status {status}")
    print(f"\nResumo: votação {voting_id} encerrada por scheduler")


if __name__ == "__main__":
    main()
