"""Testes do comando create_admin."""

import io
import sys

import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_create_admin_com_senha_via_stdin(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("SenhaForte123\n"))

    call_command(
        "create_admin",
        username="AdminInicial",
        password_stdin=True,
        verbosity=0,
    )

    user = User.objects.get(username__iexact="admininicial")
    assert user.is_admin is True
    assert user.is_active is True
    assert user.check_password("SenhaForte123") is True


def test_create_admin_rejeita_username_duplicado(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO("SenhaForte123\n"))
    call_command(
        "create_admin",
        username="AdminInicial",
        password_stdin=True,
        verbosity=0,
    )

    monkeypatch.setattr(sys, "stdin", io.StringIO("OutraSenhaForte123\n"))
    with pytest.raises(CommandError):
        call_command(
            "create_admin",
            username="admininicial",
            password_stdin=True,
            verbosity=0,
        )
