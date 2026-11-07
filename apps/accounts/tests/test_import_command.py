"""Testes do comando import_participants."""

import pytest
from django.core.management import CommandError, call_command

from apps.accounts.models import User

pytestmark = pytest.mark.django_db


def test_comando_dry_run_nao_grava(tmp_path):
    path = tmp_path / "participants.csv"
    path.write_bytes(b"username\nSpecialWeek\n")

    call_command("import_participants", file=str(path), verbosity=0)

    assert User.objects.filter(username="SpecialWeek").exists() is False


def test_comando_apply_importa(tmp_path):
    path = tmp_path / "participants.csv"
    path.write_bytes(b"username\nSpecialWeek\nTokaiTeio\n")

    call_command("import_participants", file=str(path), apply=True, verbosity=0)

    assert User.objects.filter(username="SpecialWeek").exists()
    assert User.objects.filter(username="TokaiTeio").exists()


def test_comando_com_erro_nao_grava(tmp_path):
    path = tmp_path / "participants.csv"
    path.write_bytes(b"username\nOkUser\nbad,user\n")

    with pytest.raises(CommandError):
        call_command("import_participants", file=str(path), apply=True, verbosity=0)

    assert User.objects.filter(username="OkUser").exists() is False
