"""Rejeita uma mudança de catálogo pendente pela linha de comando."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import SyncChange
from apps.catalog.services.sync import CatalogSyncError, reject_change


class Command(BaseCommand):
    help = "Rejeita uma SyncChange pendente, registrando revisor e nota."

    def add_arguments(self, parser):
        parser.add_argument("--id", type=int, required=True)
        parser.add_argument("--reviewer", required=True, help="Username do administrador")
        parser.add_argument("--note", default="")

    def handle(self, *args, **options):
        try:
            change = SyncChange.objects.get(pk=options["id"])
        except SyncChange.DoesNotExist as exc:
            raise CommandError("Mudança não encontrada.") from exc

        try:
            admin = get_user_model().objects.get(username__iexact=options["reviewer"])
        except get_user_model().DoesNotExist as exc:
            raise CommandError("Revisor não encontrado.") from exc

        try:
            reject_change(change, admin, options["note"])
        except CatalogSyncError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"Mudança #{change.pk} rejeitada por {admin.username}.")
