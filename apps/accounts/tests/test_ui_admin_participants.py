"""Contratos de apresentação da área administrativa de participantes (Fase 5)."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.accounts.models import User
from tests.factories import AdminUserFactory, ParticipantFactory

pytestmark = pytest.mark.django_db


def _login(client, user):
    client.force_login(user)
    return client


def _csv_upload(content: bytes, name: str = "participants.csv"):
    return SimpleUploadedFile(name, content, content_type="text/csv")


def test_lista_mantem_busca_acoes_e_tabela_responsiva(client):
    admin = AdminUserFactory(username="AdminUser")
    participant = ParticipantFactory(username="SpecialWeek")
    _login(client, admin)

    response = client.get(reverse("admin:participant_list"))
    html = response.content.decode()

    assert response.status_code == 200
    assert 'id="participant-search"' in html
    assert 'name="q"' in html
    assert reverse("admin:participant_create") in html
    assert reverse("admin:participant_import") in html
    assert reverse("admin:participant_edit", args=[participant.pk]) in html
    assert reverse("admin:participant_deactivate", args=[participant.pk]) in html
    assert 'data-label="Username"' in html
    assert 'data-label="Ações"' in html
    assert "admin-data-table" in html
    assert "Lista de participantes" in html
    assert 'data-confirm="Desativar este participante? Ele perde o acesso ao sistema."' in html
    assert "AdminUser" in html
    assert "Administrador — somente leitura" in html
    assert "Somente leitura" in html


def test_lista_vazia_oferece_limpar_busca(client):
    admin = AdminUserFactory()
    ParticipantFactory(username="SpecialWeek")
    _login(client, admin)

    response = client.get(reverse("admin:participant_list"), {"q": "inexistente"})
    html = response.content.decode()

    assert response.status_code == 200
    assert "Nenhum participante encontrado" in html
    assert "inexistente" in html
    assert reverse("admin:participant_list") in html


def test_formulario_associa_label_ajuda_e_erro_ao_campo(client):
    admin = AdminUserFactory()
    ParticipantFactory(username="SpecialWeek")
    _login(client, admin)

    response = client.post(
        reverse("admin:participant_create"),
        {"username": "specialweek"},
    )
    html = response.content.decode()

    assert response.status_code == 200
    assert 'for="id_username"' in html
    assert 'id="id_username"' in html
    assert 'id="username-help"' in html
    assert 'id="username-error"' in html
    assert 'role="alert"' in html
    assert "Já existe um usuário com esse username." in html
    assert "data-submit-once" in html
    assert reverse("admin:participant_list") in html
    assert User.objects.filter(username__iexact="specialweek").count() == 1


def test_importacao_mostra_duas_etapas_e_previa_valida(client):
    admin = AdminUserFactory()
    _login(client, admin)

    response = client.post(
        reverse("admin:participant_import"),
        {"file": _csv_upload(b"username\nSpecialWeek\nTokaiTeio\n")},
    )
    html = response.content.decode()

    assert response.status_code == 200
    assert "1. Validar arquivo" in html
    assert "2. Conferir prévia e importar" in html
    assert "import-steps" in html
    assert "import-preview" in html
    assert "Pronto para importar" in html
    assert 'name="action" value="apply"' in html
    assert "Confirmar importação de 2 participante(s)" in html
    assert "SpecialWeek" in html
    assert "TokaiTeio" in html
    assert User.objects.count() == 1


def test_importacao_classifica_erros_e_nao_grava(client):
    admin = AdminUserFactory()
    ParticipantFactory(username="Teste")
    _login(client, admin)

    response = client.post(
        reverse("admin:participant_import"),
        {"file": _csv_upload(b"username\nNovoUsuario\nNovoUsuario\nTeste\n")},
    )
    html = response.content.decode()

    assert response.status_code == 200
    assert "2. Corrigir arquivo" in html
    assert "A importação não foi aplicada." in html
    assert "Duplicidade no arquivo" in html
    assert "Username já cadastrado" in html
    assert "novousuario" not in {u.username.casefold() for u in User.objects.all()}
