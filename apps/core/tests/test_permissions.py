"""Testes dos helpers de autorização compartilhados."""

from types import SimpleNamespace

from apps.core.permissions import is_active_user, is_admin_user


def test_usuario_anonimo_nao_e_ativo_nem_admin():
    anonymous = SimpleNamespace(is_authenticated=False, is_active=False, is_admin=False)

    assert is_active_user(anonymous) is False
    assert is_admin_user(anonymous) is False


def test_participante_ativo_nao_e_admin():
    participant = SimpleNamespace(is_authenticated=True, is_active=True, is_admin=False)

    assert is_active_user(participant) is True
    assert is_admin_user(participant) is False


def test_administrador_inativo_nao_e_admin():
    admin = SimpleNamespace(is_authenticated=True, is_active=False, is_admin=True)

    assert is_admin_user(admin) is False


def test_administrador_ativo_e_admin():
    admin = SimpleNamespace(is_authenticated=True, is_active=True, is_admin=True)

    assert is_admin_user(admin) is True
