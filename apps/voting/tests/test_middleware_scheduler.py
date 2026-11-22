"""Scheduler acionado pelo início de requisições dinâmicas."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.conf import settings
from django.test import Client, override_settings
from django.utils import timezone

from apps.catalog.models import Aptitude
from apps.voting.middleware import RequestSchedulerMiddleware
from apps.voting.models import Mode, Voting, VotingStatus
from apps.voting.services import scheduler
from apps.voting.services.eligibility import add_default_eligible
from tests.factories import (
    CharacterFactory,
    CharacterVersionAptitudeFactory,
    CharacterVersionFactory,
    ParticipantFactory,
    VotingFactory,
)

pytestmark = pytest.mark.django_db

CUTOFF = date(2026, 12, 1)

ON_REQUEST_MIDDLEWARE = [
    *[item for item in settings.MIDDLEWARE if not item.startswith("whitenoise.")],
    "apps.voting.middleware.RequestSchedulerMiddleware",
]


def make_catalog(count: int) -> None:
    for index in range(count):
        character = CharacterFactory(stable_id=f"personagem-{index}")
        version = CharacterVersionFactory(
            character=character,
            stable_id=f"personagem-{index}-v1",
            release_date_global=CUTOFF,
        )
        for category, value in (
            ("strategy", "pace"),
            ("distance", "medium"),
            ("surface", "turf"),
        ):
            CharacterVersionAptitudeFactory(
                version=version,
                aptitude=Aptitude.objects.get(category=category, value=value),
            )


def make_due_voting() -> Voting:
    voting = VotingFactory(
        status=VotingStatus.DRAFT,
        catalog_cutoff_date=CUTOFF,
        open_mode=Mode.AUTOMATIC,
        close_mode=Mode.AUTOMATIC,
        opens_at=timezone.now() - timedelta(minutes=5),
        closes_at=timezone.now() + timedelta(hours=1),
    )
    ParticipantFactory()
    add_default_eligible(voting)
    make_catalog(voting.choices_count)
    voting.status = VotingStatus.SCHEDULED
    voting.save(update_fields=["status"])
    return voting


def zero_report(**overrides) -> scheduler.SchedulerReport:
    return scheduler.SchedulerReport(**overrides)


def fake_request(method: str = "GET", path: str = "/"):
    return type("Request", (), {"method": method, "path": path})()


def test_middleware_nao_instalado_no_modo_external():
    assert "apps.voting.middleware.RequestSchedulerMiddleware" not in settings.MIDDLEWARE
    assert settings.DJANGO_SCHEDULER_MODE == "external"


def test_modo_on_request_executa_uma_vez_por_intervalo(monkeypatch, client: Client):
    calls = []

    def fake_process(*args, **kwargs):
        calls.append(1)
        return zero_report()

    monkeypatch.setattr(scheduler, "process_due_transitions", fake_process)

    with override_settings(
        DJANGO_SCHEDULER_MODE="on_request",
        MIDDLEWARE=ON_REQUEST_MIDDLEWARE,
        DJANGO_SCHEDULER_TICK_INTERVAL=60,
    ):
        # /health/ não dispara o tick; estas duas rotas dinâmicas disparam.
        assert client.get("/entrar/").status_code == 200
        assert client.get("/").status_code == 302

    assert len(calls) == 1


def test_tick_ignora_health_estaticos_midia_e_metodos_de_escrita(monkeypatch):
    calls = []
    monkeypatch.setattr(
        scheduler, "process_due_transitions", lambda *a, **k: calls.append(1) or zero_report()
    )
    middleware = RequestSchedulerMiddleware(lambda request: 200)

    for path in ("/health/", "/static/app.css", "/media/characters/x.webp"):
        middleware(fake_request(path=path))
    middleware(fake_request(method="POST", path="/votacoes/1/"))

    assert calls == []


def test_tick_falho_nao_derruba_requisicao(monkeypatch, caplog):
    def boom(*args, **kwargs):
        raise RuntimeError("banco indisponível")

    monkeypatch.setattr(scheduler, "process_due_transitions", boom)
    middleware = RequestSchedulerMiddleware(lambda request: 200)

    with caplog.at_level("ERROR", logger="apps.voting.scheduler"):
        response = middleware(fake_request(path="/"))

    assert response == 200
    assert "Scheduler on_request falhou" in caplog.text


def test_intervalo_zero_desativa_o_tick(monkeypatch):
    calls = []
    monkeypatch.setattr(
        scheduler, "process_due_transitions", lambda *a, **k: calls.append(1) or zero_report()
    )
    middleware = RequestSchedulerMiddleware(lambda request: 200)
    middleware.interval = 0

    middleware(fake_request(path="/"))

    assert calls == []


def test_requisicao_abre_votacao_devida_antes_da_view():
    voting = make_due_voting()
    seen = {}
    middleware = RequestSchedulerMiddleware(lambda request: 200)

    # A view só é chamada depois do tick: quando ela olha o banco, já está aberta.
    def view(request):
        seen["status"] = Voting.objects.get(pk=voting.pk).status
        return 200

    middleware.get_response = view
    middleware(fake_request(path="/"))

    voting.refresh_from_db()
    assert seen["status"] == VotingStatus.OPEN
    assert voting.status == VotingStatus.OPEN
