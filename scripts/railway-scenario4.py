"""Cenário 4 do plano: janela perdida → votação cancelada.

Regra crítica: **nenhuma requisição HTTP** entre o agendamento e o fim da janela
— login, páginas e até /health/ disparam o tick do scheduler e abririam a
votação antes da hora. Por isso a criação, a espera e as consultas usam apenas o
banco (SSH), e só a última requisição é HTTP, depois que a janela fechou.

    ADMIN_PASSWORD=... python3 scripts/railway-scenario4.py --base-url https://...
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from datetime import timezone as dt_timezone

PRELUDE = (
    "import os, django\n"
    "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings.prod')\n"
    "django.setup()\n"
)


def fail(message: str) -> None:
    print(f"FALHA: {message}")
    sys.exit(1)


def ssh_python(code: str) -> str:
    result = subprocess.run(
        [
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
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        fail(f"ssh falhou: {result.stderr[-500:]}")
    return result.stdout.strip().splitlines()[-1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.environ.get("APP_BASE_URL", ""))
    parser.add_argument("--admin-username", default=os.environ.get("ADMIN_USERNAME", "Jota"))
    parser.add_argument("--open-in", type=int, default=2)
    parser.add_argument("--close-in", type=int, default=3)
    args = parser.parse_args()

    if not args.base_url:
        fail("informe --base-url")
    base = args.base_url.rstrip("/")
    title = f"TESTE janela perdida {date.today().isoformat()}"

    tz = dt_timezone(timedelta(hours=-3))
    opens_at = datetime.now(dt_timezone.utc) + timedelta(minutes=args.open_in)
    closes_at = datetime.now(dt_timezone.utc) + timedelta(minutes=args.close_in)
    print(
        f"1) criando '{title}' com janela "
        f"{opens_at.astimezone(tz):%H:%M}–{closes_at.astimezone(tz):%H:%M} local"
    )

    created = ssh_python(
        PRELUDE
        + "from datetime import datetime, timezone, timedelta\n"
        "from apps.accounts.services.participants import create_participant\n"
        "from apps.accounts.models import User\n"
        "from apps.voting.services.lifecycle import create_and_schedule_voting\n"
        "if not User.objects.filter(username='teste_ana').exists():\n"
        "    create_participant('teste_ana')\n"
        f"admin = User.objects.get(username='{args.admin_username}')\n"
        f"opens = datetime.now(timezone.utc) + timedelta(minutes={args.open_in})\n"
        f"closes = datetime.now(timezone.utc) + timedelta(minutes={args.close_in})\n"
        "result = create_and_schedule_voting({\n"
        f"    'title': {title!r},\n"
        "    'description': 'Janela perdida: abertura e encerramento automaticos sem acesso.',\n"
        "    'choices_count': 1,\n"
        "    'catalog_cutoff_date': datetime.now(timezone.utc).date(),\n"
        "    'open_mode': 'automatic',\n"
        "    'close_mode': 'automatic',\n"
        "    'opens_at': opens,\n"
        "    'closes_at': closes,\n"
        "}, admin)\n"
        "v = result.voting\n"
        "print(v.pk, v.status, result.scheduled, v.opens_at.isoformat(), v.closes_at.isoformat())\n"
    )
    voting_id_text, status_text, scheduled, opens_iso, closes_iso = created.split(" ", 4)
    voting_id = int(voting_id_text)
    print(f"   id={voting_id} status={status_text} agendada={scheduled}")
    if status_text != "scheduled":
        fail(f"a votação não ficou agendada ({status_text})")

    # Acorda o serviço sem disparar o tick, antes da janela abrir.
    print("2) acordando o serviço via /health/ (não executa o scheduler)")
    subprocess.run(
        ["curl", "--fail", "--silent", "--show-error", "--max-time", "60", f"{base}/health/"],
        check=False,
        capture_output=True,
    )

    target = datetime.fromisoformat(closes_iso) + timedelta(seconds=30)
    print(f"3) esperando o fim da janela em {target.astimezone(tz):%H:%M:%S} local, sem acesso ao site")
    while datetime.now(dt_timezone.utc) < target:
        time.sleep(min(30, max(1, (target - datetime.now(dt_timezone.utc)).total_seconds())))

    before = ssh_python(
        PRELUDE
        + f"from apps.voting.models import Voting\nv = Voting.objects.get(pk={voting_id})\n"
        "print(v.status, v.opened_at, v.cancelled_at)\n"
    )
    print("   banco ANTES da requisição:", before)

    hit_at = datetime.now(dt_timezone.utc)
    status = subprocess.run(
        ["curl", "--silent", "--output", "/dev/null", "--write-out", "%{http_code}", f"{base}/"],
        capture_output=True,
        text=True,
    ).stdout
    print(f"4) primeira requisição dinâmica GET / -> {status} às {hit_at:%H:%M:%S} UTC")

    after = ssh_python(
        PRELUDE
        + "from apps.voting.models import Voting, Ballot\n"
        f"v = Voting.objects.get(pk={voting_id})\n"
        "print(v.status, v.opened_at, v.closed_at, v.cancelled_at, Ballot.objects.filter(voting=v).count())\n"
    )
    print("   banco DEPOIS (status, opened, closed, cancelled, cédulas):", after)

    print(f"\nResumo: votação {voting_id} — {title}")


if __name__ == "__main__":
    main()
