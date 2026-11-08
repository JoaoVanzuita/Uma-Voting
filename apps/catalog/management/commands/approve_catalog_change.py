"""Aprova uma mudança de catálogo pendente pela linha de comando."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.catalog.models import SyncChange
from apps.catalog.services.sync import CatalogSyncError, approve_change


class Command(BaseCommand):
    help = "Aprova uma SyncChange pendente aplicando o payload proposto."

    def add_arguments(self, parser):
        parser.add_argument("--id", type=int, required=True)
        parser.add_argument("--reviewer", required=True, help="Username do administrador")

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
            approve_change(change, admin)
        except CatalogSyncError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"Mudança #{change.pk} aprovada por {admin.username}.")
