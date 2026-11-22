"""Remove os dados de teste de votações criados pelo plano de testes.

Uso (no serviço `web`, via `railway ssh`):

    python manage.py purge_test_votings --prefix "TESTE " --dry-run
    python manage.py purge_test_votings --prefix "TESTE " --apply

Só apaga votações cujo título começa pelo prefixo informado. Votações com
cédulas confirmadas são **canceladas** (o cancelamento remove as cédulas pela
regra do app) em vez de excluídas, preservando o histórico. Participantes e
catálogo nunca são tocados.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.voting.models import Ballot, Voting, VotingStatus
from apps.voting.services.lifecycle import cancel_voting

DEFAULT_PREFIX = "TESTE "


class Command(BaseCommand):
    help = "Remove ou cancela votações de teste a partir do prefixo do título."

    def add_arguments(self, parser):
        parser.add_argument("--prefix", default=DEFAULT_PREFIX)
        parser.add_argument("--dry-run", action="store_true", help="Apenas relata (padrão).")
        parser.add_argument("--apply", action="store_true", help="Executa a limpeza.")
        parser.add_argument("--json", action="store_true", dest="as_json")

    def handle(self, *args, **options):
        if options["dry_run"] and options["apply"]:
            raise CommandError("Use --dry-run ou --apply, não os dois.")
        prefix = options["prefix"]
        if not prefix.strip():
            raise CommandError("Informe um prefixo não vazio para limitar a limpeza.")

        votings = list(Voting.objects.filter(title__startswith=prefix).order_by("pk"))
        report = {"prefix": prefix, "found": len(votings), "deleted": [], "cancelled": []}

        for voting in votings:
            voting_pk, voting_title, voting_status = voting.pk, voting.title, voting.status
            has_ballots = Ballot.objects.filter(voting=voting).exists()
            if voting.status == VotingStatus.CANCELLED and not has_ballots:
                outcome = "deleted"
            elif has_ballots or voting.status == VotingStatus.CLOSED:
                outcome = "cancelled"
            else:
                outcome = "deleted"

            if options["apply"]:
                if outcome == "deleted":
                    with transaction.atomic():
                        voting.delete()
                else:
                    cancel_voting(voting, reason="limpeza de teste")
            report[outcome].append(
                {"id": voting_pk, "title": voting_title, "status": voting_status}
            )

        if options["as_json"]:
            self.stdout.write(json.dumps(report, ensure_ascii=False))
        else:
            mode = "apply" if options["apply"] else "dry-run"
            self.stdout.write(
                f"[{mode}] prefixo='{prefix}' encontradas={report['found']} "
                f"excluidas={len(report['deleted'])} canceladas={len(report['cancelled'])}"
            )
            for item in report["deleted"] + report["cancelled"]:
                self.stdout.write(f"  {item['id']} {item['status']} {item['title']}")
