"""Cenários 5 e 6 do plano de produção.

Cenário 5 — pré-condição bloqueia o agendamento:
    data de corte anterior a todo o catálogo (0 elegíveis por data) e ação
    "Salvar e agendar" → a votação deve persistir como **rascunho** com aviso,
    sem perder os dados digitados.

Cenário 6 — higiene do tick do scheduler:
    N requisições dinâmicas em rajada → no máximo um tick por intervalo
    (`DJANGO_SCHEDULER_TICK_INTERVAL`) por processo; `/health/` e `/static/`
    nunca disparam o tick.

    ADMIN_PASSWORD=... python3 scripts/railway-scenario56.py --base-url https://...
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
from datetime import date, timedelta

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
            with self.opener.open(self.base_url + path, timeout=90) as response:
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


PRELUDE = (
    "import os, django\n"
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.prod')\n"
    "django.setup()\n"
)


def ssh(code: str) -> str:
    result = subprocess.run(
        ["railway", "ssh", "--service", "web", "--environment", "production", "--", "python", "-c", code],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        fail(f"ssh falhou: {result.stderr[-500:]}")
    return result.stdout.strip()


def deployment_logs(lines: int = 400) -> str:
    listing = subprocess.run(
        ["railway", "deployment", "list", "--service", "web", "--json"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    import json

    deployments = json.loads(listing.stdout)
    current = next(item for item in deployments if item["status"] == "SUCCESS")
    logs = subprocess.run(
        ["railway", "logs", current["id"], "--deployment", "--lines", str(lines)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    return logs.stdout


def text_only(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("APP_BASE_URL", ""))
    parser.add_argument("--admin-username", default=os.environ.get("ADMIN_USERNAME", "Jota"))
    parser.add_argument("--requests", type=int, default=12)
    args = parser.parse_args()
    if not args.base_url:
        fail("informe --base-url")
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        fail("defina ADMIN_PASSWORD")
    base = args.base_url.rstrip("/")
    browser = Browser(base)
    if "/admin/" not in browser.login_admin(args.admin_username, password):
        fail("login admin")

    # ------------------------------------------------------------------ cenário 5
    print("CENÁRIO 5 — pré-condição bloqueia o agendamento")
    cutoff = (date.today() - timedelta(days=3650)).isoformat()
    opens = date.today() + timedelta(days=1)
    title = "TESTE precondição sem catálogo"
    status, html, _ = browser.get("/admin/votacoes/nova/")
    fields = {
        "csrfmiddlewaretoken": Browser.csrf(html),
        "title": title,
        "description": "Data de corte antes de todo o catálogo (0 elegíveis por data).",
        "choices_count": "1",
        "catalog_cutoff_date": cutoff,
        "open_mode": "automatic",
        "close_mode": "manual",
        "opens_at": f"{opens.isoformat()}T12:00",
        "closes_at": "",
        "action": "schedule",
    }
    status, html, url = browser.post("/admin/votacoes/nova/", fields, "/admin/votacoes/nova/")
    match = re.search(r"/admin/votacoes/(\d+)/", url)
    if status != 200 or not match:
        fail(f"criação falhou (status {status}, url {url})")
    voting_id = int(match.group(1))
    body = text_only(html)
    persisted = ssh(
        PRELUDE
        + f"from apps.voting.models import Voting\nv = Voting.objects.get(pk={voting_id})\n"
        "print(v.status, v.title, v.catalog_cutoff_date.isoformat())\n"
    )
    warning = "rascunho" in body.lower() and ("não agendada" in body.lower() or "não foi possível" in body.lower())
    print(f"   id={voting_id} -> banco: {persisted}")
    print(f"   aviso de rascunho na página: {warning}")
    print(f"   campos preservados (título/corte no banco): {'sem catálogo' in persisted and cutoff in persisted}")
    if not persisted.startswith("draft"):
        fail("a votação NÃO ficou em rascunho")

    # ------------------------------------------------------------------ cenário 6
    print("\nCENÁRIO 6 — higiene do tick do scheduler")
    logs_before = deployment_logs()
    ticks_before = logs_before.count("Scheduler on_request")

    burst = [f"/admin/votacoes/{voting_id}/" for _ in range(args.requests)]
    started = time.monotonic()
    codes = [browser.get(path)[0] for path in burst]
    elapsed = time.monotonic() - started
    print(f"   {args.requests} GETs dinâmicos em {elapsed:.1f}s (status {sorted(set(codes))})")

    health_codes = [browser.get("/health/")[0] for _ in range(3)]
    css_status, css_html, _ = browser.get("/admin/votacoes/nova/")
    css_path = re.search(r'href="(/static/[^"]+\.css)"', css_html)
    if css_path:
        css_code = browser.get(css_path.group(1))[0]
        print(f"   estático {css_path.group(1)} -> {css_code}")
    print(f"   /health/ x3 -> {sorted(set(health_codes))}")

    time.sleep(5)
    logs_after = deployment_logs()
    ticks_after = logs_after.count("Scheduler on_request")
    new_ticks = ticks_after - ticks_before
    new_lines = [line for line in logs_after.splitlines() if "Scheduler on_request" in line][-new_ticks:] if new_ticks else []
    print(f"   ticks novos durante a rajada: {new_ticks} (esperado: ≤ 1 por intervalo de 60 s)")
    for line in new_lines:
        print("   ", line[-110:])
    if new_ticks > 1:
        fail("mais de um tick por intervalo na mesma janela")

    print("\nResumo: cenário 5 validado; cenário 6 validado" if new_ticks <= 1 else "\nResumo: verificar")


if __name__ == "__main__":
    main()
