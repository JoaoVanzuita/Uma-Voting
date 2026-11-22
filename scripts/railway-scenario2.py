"""Cenário 2 do plano: agendamento com abertura automática (scheduler sob demanda).

Prova que a transição acontece **na primeira requisição após o horário**, antes
de a view renderizar, sem cron e sem serviço permanente — o modelo do Railway Free.

    ADMIN_PASSWORD=... python3 scripts/railway-scenario2.py --base-url https://...

Passos:
  1. cria 2 participantes de teste (elegíveis são todos os usuários ativos);
  2. cria a votação com abertura automática em `+N min` e encerramento manual,
     usando a ação "Salvar e agendar";
  3. faz o login do participante **antes** do horário (login é requisição dinâmica
     e dispararia o tick), e espera sem acessar o site;
  4. faz **uma única** `GET /` após o horário e confere `status` e `opened_at`.
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

ID_RE = re.compile(r"/admin/votacoes/(\d+)/")
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


PRELUDE = (
    "import os, django\n"
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.prod')\n"
    "django.setup()\n"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("APP_BASE_URL", ""))
    parser.add_argument("--admin-username", default=os.environ.get("ADMIN_USERNAME", "Jota"))
    parser.add_argument("--delay-minutes", type=int, default=2)
    parser.add_argument("--participant", default="teste_ana")
    args = parser.parse_args()

    if not args.base_url:
        fail("informe --base-url")
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        fail("defina ADMIN_PASSWORD")
    base = args.base_url.rstrip("/")

    print("1) participantes de teste")
    print(
        ssh_python(
            PRELUDE + "from apps.accounts.services.participants import create_participant\n"
            "from apps.accounts.models import User\n"
            "for name in ('teste_ana', 'teste_bruno'):\n"
            "    if not User.objects.filter(username=name).exists():\n"
            "        create_participant(name)\n"
            "print(list(User.objects.filter(is_admin=False).values_list('username', flat=True)))\n"
        )
    )

    admin = Browser(base)
    url = admin.login_admin(args.admin_username, password)
    if "/admin/" not in url:
        fail(f"login admin ({url})")

    now = datetime.now(UTC)
    opens_at = now + timedelta(minutes=args.delay_minutes)
    local = opens_at.astimezone(dt_timezone(timedelta(hours=-3)))
    title = f"TESTE agendada {date.today().isoformat()}"

    print(f"2) criando e agendando '{title}' para {local:%Y-%m-%dT%H:%M} (local)")
    status, html, _ = admin.get("/admin/votacoes/nova/")
    fields = {
        "csrfmiddlewaretoken": Browser.csrf(html),
        "title": title,
        "description": "Teste de abertura automática sob demanda.",
        "choices_count": "1",
        "catalog_cutoff_date": date.today().isoformat(),
        "open_mode": "automatic",
        "close_mode": "manual",
        "opens_at": f"{local:%Y-%m-%dT%H:%M}",
        "closes_at": "",
        "action": "schedule",
    }
    status, html, url = admin.post("/admin/votacoes/nova/", fields, "/admin/votacoes/nova/")
    match = ID_RE.search(url)
    if status != 200 or not match:
        fail(f"agendamento falhou (status {status}, url {url})")
    voting_id = int(match.group(1))
    state = ssh_python(
        PRELUDE + f"from apps.voting.models import Voting\nv = Voting.objects.get(pk={voting_id})\n"
        "print(v.status)\n"
    )
    print(f"   id={voting_id} status={state}")

    print("3) login do participante (antes do horário) e espera sem requisições")
    participant = Browser(base)
    participant.login_participant(args.participant)
    target = opens_at + timedelta(seconds=70)
    while datetime.now(UTC) < target:
        time.sleep(min(30, max(1, (target - datetime.now(UTC)).total_seconds())))

    hit_at = datetime.now(UTC)
    status, html, url = participant.get("/")
    print(f"4) primeira GET / após o horário: {status} em {hit_at:%H:%M:%S} UTC")

    after = ssh_python(
        PRELUDE + f"from apps.voting.models import Voting\nv = Voting.objects.get(pk={voting_id})\n"
        "print(v.status, v.opens_at.isoformat(), v.opened_at.isoformat() if v.opened_at else None)"
        "\n"
    )
    print("   banco:", after)

    status, html, url = participant.get(f"/votacoes/{voting_id}/")
    votable = status == 200 and 'name="character_ids"' in html
    print(f"   participante vê a votação aberta: {votable} (status {status})")
    print(f"\nResumo: votação {voting_id} — {title}")


if __name__ == "__main__":
    main()
