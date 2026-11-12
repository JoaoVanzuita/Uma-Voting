"""Testes de integração da área administrativa de participantes."""

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


def test_lista_mostra_participantes_e_administrador_read_only(client):
    admin = AdminUserFactory(username="AdminUser")
    ParticipantFactory(username="SpecialWeek")
    _login(client, admin)

    response = client.get(reverse("admin:participant_list"))
    html = response.content.decode()

    assert response.status_code == 200
    assert "SpecialWeek" in html
    assert "AdminUser" in html
    assert "Administrador — somente leitura" in html
    assert "Somente leitura" in html


def test_lista_pesquisa_por_username(client):
    admin = AdminUserFactory()
    ParticipantFactory(username="SpecialWeek")
    ParticipantFactory(username="TokaiTeio")
    _login(client, admin)

    response = client.get(reverse("admin:participant_list"), {"q": "tokai"})
    html = response.content.decode()

    assert "TokaiTeio" in html
    assert "SpecialWeek" not in html


def test_participante_nao_acessa_area_de_participantes(client):
    participant = ParticipantFactory()
    _login(client, participant)

    response = client.get(reverse("admin:participant_list"))

    assert response.status_code == 403


def test_visitante_e_redirecionado_ao_login_administrativo(client):
    response = client.get(reverse("admin:participant_list"))

    assert response.status_code == 302
    assert response.url.startswith(reverse("admin:login"))


def test_cadastra_participante(client):
    admin = AdminUserFactory()
    _login(client, admin)

    response = client.post(
        reverse("admin:participant_create"),
        {"username": "SpecialWeek"},
    )

    assert response.status_code == 302
    assert response.url == reverse("admin:participant_list")
    participant = User.objects.get(username="SpecialWeek")
    assert participant.is_admin is False
    assert participant.is_active is True
    assert participant.has_usable_password() is False


def test_cadastro_duplicado_case_insensitive_mostra_erro(client):
    admin = AdminUserFactory()
    ParticipantFactory(username="SpecialWeek")
    _login(client, admin)

    response = client.post(
        reverse("admin:participant_create"),
        {"username": "specialweek"},
    )

    assert response.status_code == 200
    assert "Já existe um usuário com esse username." in response.content.decode()
    assert User.objects.filter(username__iexact="specialweek").count() == 1


def test_edita_username_do_participante(client):
    admin = AdminUserFactory()
    participant = ParticipantFactory(username="Antigo")
    _login(client, admin)

    response = client.post(
        reverse("admin:participant_edit", args=[participant.pk]),
        {"username": "NovoNome"},
    )

    assert response.status_code == 302
    participant.refresh_from_db()
    assert participant.username == "NovoNome"


def test_edicao_de_administrador_e_bloqueada(client):
    admin = AdminUserFactory()
    other_admin = AdminUserFactory(username="OutroAdmin")
    _login(client, admin)

    response = client.get(reverse("admin:participant_edit", args=[other_admin.pk]))

    assert response.status_code == 403


def test_desativa_participante_e_bloqueia_login(client):
    admin = AdminUserFactory()
    participant = ParticipantFactory(username="SpecialWeek")
    _login(client, admin)

    response = client.post(
        reverse("admin:participant_deactivate", args=[participant.pk]),
    )

    assert response.status_code == 302
    participant.refresh_from_db()
    assert participant.is_active is False

    login_client = client.__class__()
    response = login_client.post(
        reverse("participant:login"),
        {"username": "SpecialWeek"},
    )
    assert response.status_code == 200
    assert "Não foi possível entrar com esse username." in response.content.decode()


def test_desativacao_de_administrador_e_bloqueada(client):
    admin = AdminUserFactory()
    other_admin = AdminUserFactory(username="OutroAdmin")
    _login(client, admin)

    response = client.post(
        reverse("admin:participant_deactivate", args=[other_admin.pk]),
    )

    assert response.status_code == 403
    other_admin.refresh_from_db()
    assert other_admin.is_active is True


def test_desativacao_exige_post(client):
    admin = AdminUserFactory()
    participant = ParticipantFactory()
    _login(client, admin)

    response = client.get(reverse("admin:participant_deactivate", args=[participant.pk]))

    assert response.status_code == 405


# ---------------------------------------------------------------------------
# Importação pela interface
# ---------------------------------------------------------------------------


def test_importacao_preview_e_confirmacao(client):
    admin = AdminUserFactory()
    _login(client, admin)

    preview = client.post(
        reverse("admin:participant_import"),
        {"file": _csv_upload(b"username\nSpecialWeek\nTokaiTeio\n")},
    )
    preview_html = preview.content.decode()

    assert preview.status_code == 200
    assert "SpecialWeek" in preview_html
    assert "Confirmar importação de 2 participante(s)" in preview_html
    assert User.objects.count() == 1  # apenas o administrador

    apply_response = client.post(
        reverse("admin:participant_import"),
        {"action": "apply"},
        follow=True,
    )

    assert apply_response.status_code == 200
    assert "2 participante(s) importado(s) com sucesso." in apply_response.content.decode()
    assert User.objects.filter(username="SpecialWeek").exists()
    assert User.objects.filter(username="TokaiTeio").exists()


def test_importacao_invalida_nao_grava_e_mostra_erros(client):
    admin = AdminUserFactory()
    _login(client, admin)

    response = client.post(
        reverse("admin:participant_import"),
        {"file": _csv_upload(b"username\nSpecial,Week\n")},
    )
    html = response.content.decode()

    assert response.status_code == 200
    assert "Vírgula não suportada no username." in html
    assert "A importação não foi aplicada." in html
    assert User.objects.filter(username__icontains="Special").exists() is False


def test_apply_sem_preview_pendente_redireciona_com_erro(client):
    admin = AdminUserFactory()
    _login(client, admin)

    response = client.post(
        reverse("admin:participant_import"),
        {"action": "apply"},
        follow=True,
    )

    assert response.status_code == 200
    assert "Nenhuma importação pendente" in response.content.decode()
