"""Testes da importação atômica de participantes por CSV."""

import io

import pytest

from apps.accounts.models import User
from apps.accounts.services.imports import (
    MAX_FILE_SIZE,
    import_participants,
    import_rows,
)
from tests.factories import ParticipantFactory

pytestmark = pytest.mark.django_db


def _file(content: bytes) -> io.BytesIO:
    return io.BytesIO(content)


def test_importa_csv_valido_com_cabecalho():
    report = import_participants(
        _file(b"username\nSpecialWeek\nTokaiTeio\n"),
        apply=True,
    )

    assert report.has_errors is False
    assert report.imported_count == 2
    assert User.objects.filter(username="SpecialWeek").exists()
    assert User.objects.filter(username="TokaiTeio").exists()


def test_importa_csv_valido_sem_cabecalho():
    report = import_participants(_file(b"SpecialWeek\nTokaiTeio\n"), apply=True)

    assert report.imported_count == 2
    assert report.valid_rows == ["SpecialWeek", "TokaiTeio"]


def test_ignora_linhas_vazias():
    report = import_participants(
        _file(b"\nusername\n\nSpecialWeek\n\n"),
        apply=True,
    )

    assert report.imported_count == 1
    assert report.total_lines == 1


def test_dry_run_nao_grava():
    report = import_participants(_file(b"username\nSpecialWeek\n"), apply=False)

    assert report.imported_count == 0
    assert report.applied is False
    assert report.valid_rows == ["SpecialWeek"]
    assert User.objects.filter(username="SpecialWeek").exists() is False


def test_duplicidade_no_arquivo_rejeita_tudo():
    report = import_participants(
        _file(b"username\nSpecialWeek\nspecialweek\nOutro\n"),
    )

    assert report.has_errors is True
    assert "Já existe" not in report.errors[0].message
    assert report.errors[0].line == 3
    assert report.imported_count == 0


def test_duplicidade_com_banco_rejeita_tudo():
    ParticipantFactory(username="SpecialWeek")

    report = import_participants(
        _file(b"username\nspecialweek\nNovoUsuario\n"),
        apply=True,
    )

    assert report.has_errors is True
    assert report.imported_count == 0
    assert User.objects.filter(username="NovoUsuario").exists() is False


def test_arquivo_vazio_e_rejeitado():
    report = import_participants(_file(b"   \n\n"))

    assert report.has_errors is True


def test_arquivo_apenas_com_cabecalho_e_rejeitado():
    report = import_participants(_file(b"username\n"))

    assert report.has_errors is True


def test_encoding_invalido_e_rejeitado():
    report = import_participants(_file(b"\xff\xfeSpecialWeek\n"))

    assert report.has_errors is True
    assert "UTF-8" in report.errors[0].message


def test_bom_utf8_e_aceito():
    report = import_participants(
        _file(b"\xef\xbb\xbfusername\nSpecialWeek\n"),
        apply=True,
    )

    assert report.imported_count == 1
    assert User.objects.filter(username="SpecialWeek").exists()


def test_linha_com_multiplas_colunas_e_rejeitada():
    report = import_participants(_file(b"username\nSpecial,Week\n"))

    assert report.has_errors is True
    assert report.errors[0].line == 2
    assert "Vírgula" in report.errors[0].message


def test_caractere_de_controle_e_rejeitado():
    report = import_participants(_file(b"username\nSpecial\x01Week\n"))

    assert report.has_errors is True
    assert "controle" in report.errors[0].message


def test_username_longo_demais_e_rejeitado():
    report = import_participants(_file(b"username\n" + b"a" * 151 + b"\n"))

    assert report.has_errors is True
    assert "150" in report.errors[0].message


def test_arquivo_acima_do_limite_e_rejeitado():
    report = import_participants(_file(b"a" * (MAX_FILE_SIZE + 1)))

    assert report.has_errors is True
    assert "1 MB" in report.errors[0].message


def test_importacao_e_atomica_com_uma_linha_invalida():
    report = import_participants(
        _file(b"username\nUsuarioValido\nUsuario,Invalido\n"),
        apply=True,
    )

    assert report.has_errors is True
    assert report.imported_count == 0
    assert User.objects.filter(username="UsuarioValido").exists() is False


def test_import_rows_revalida_duplicidade_no_banco():
    ParticipantFactory(username="SpecialWeek")

    report = import_rows(["SpecialWeek", "NovoUsuario"], apply=True)

    assert report.has_errors is True
    assert report.imported_count == 0
    assert User.objects.filter(username="NovoUsuario").exists() is False
