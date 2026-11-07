"""Comando para provisionar um administrador inicial."""

from __future__ import annotations

import getpass
import sys

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.services.auth import create_admin


class Command(BaseCommand):
    help = "Cria um administrador inicial com username e senha."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            required=True,
            help="Username do administrador.",
        )
        parser.add_argument(
            "--password-stdin",
            action="store_true",
            help="Lê a senha da entrada padrão (não use senha em argumento).",
        )

    def handle(self, *args, **options):
        username = options["username"].strip()
        password = self._read_password(options["password_stdin"])

        try:
            validate_password(password)
        except ValidationError as exc:
            raise CommandError("Senha inválida: " + " ".join(exc.messages)) from exc

        try:
            user = create_admin(username, password)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(f"Administrador '{user.username}' criado com sucesso.")
        )

    def _read_password(self, use_stdin: bool) -> str:
        if use_stdin:
            password = sys.stdin.readline().rstrip("\n")
            if not password:
                raise CommandError("Nenhuma senha foi informada na entrada padrão.")
            return password

        password = getpass.getpass("Senha: ")
        confirmation = getpass.getpass("Confirme a senha: ")
        if password != confirmation:
            raise CommandError("As senhas não coincidem.")
        if not password:
            raise CommandError("A senha é obrigatória.")
        return password
