"""Testes do ciclo de vida das votações (US6)."""

from __future__ import annotations

from datetime import date, timedelta
from itertools import count

import pytest
from django.utils import timezone

from apps.catalog.models import Aptitude
from apps.core.exceptions import PreconditionError
from apps.voting.models import (
    Ballot,
    Mode,
    Voting,
    VotingCharacterSnapshot,
    VotingStatus,
)
from apps.voting.services.ballots import submit_ballot
from apps.voting.services.eligibility import add_default_eligible
from apps.voting.services.lifecycle import (
    VotingStateError,
    cancel_voting,
    close_voting,
    open_voting,
)
from tests.factories import (
    CharacterFactory,
    CharacterVersionAptitudeFactory,
    CharacterVersionFactory,
    ParticipantFactory,
    VotingFactory,
)

pytestmark = pytest.mark.django_db

CUTOFF = date(2026, 12, 1)
_CATALOG_SEQ = count()


def make_catalog(count: int, *, release_date: date = CUTOFF, prefix: str = "") -> None:
    for _index in range(count):
        index = next(_CATALOG_SEQ)
        character = CharacterFactory(
            stable_id=f"{prefix}personagem-{index}",
            display_name=f"{prefix}Personagem {index}",
        )
        version = CharacterVersionFactory(
            character=character,
            stable_id=f"{prefix}personagem-{index}-v1",
            display_name=f"{prefix}Versão {index}",
            release_date_global=release_date,
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


def make_draft(choices_count: int = 3, **overrides) -> Voting:
    voting = VotingFactory(
        status=VotingStatus.DRAFT,
        choices_count=choices_count,
        catalog_cutoff_date=CUTOFF,
        **overrides,
    )
    ParticipantFactory()
    add_default_eligible(voting)
    return voting


def make_scheduled(*, opens_at, closes_at, choices_count: int = 3) -> Voting:
    voting = make_draft(
        choices_count=choices_count,
        open_mode=Mode.AUTOMATIC,
        close_mode=Mode.AUTOMATIC,
        opens_at=opens_at,
        closes_at=closes_at,
    )
    make_catalog(choices_count)
    voting.status = VotingStatus.SCHEDULED
    voting.save(update_fields=["status"])
    return voting


def future(hours: int = 1):
    return timezone.now() + timedelta(hours=hours)


def test_abertura_manual_cria_snapshots_e_congela_dados():
    voting = make_draft(choices_count=3)
    make_catalog(3)

    opened = open_voting(voting, "admin")

    opened.refresh_from_db()
    assert opened.status == VotingStatus.OPEN
    assert opened.opened_at is not None
    assert opened.eligible_frozen_at is not None
    assert opened.catalog_frozen_at is not None
    assert VotingCharacterSnapshot.objects.filter(voting=opened).count() == 3
    snapshot = VotingCharacterSnapshot.objects.filter(voting=opened).first()
    assert snapshot.version_snapshots.count() == 1
    assert snapshot.version_snapshots.first().aptitude_snapshots.count() == 3


def test_abertura_respeita_data_de_corte():
    voting = make_draft(choices_count=2)
    make_catalog(2, release_date=CUTOFF)
    make_catalog(1, release_date=date(2027, 1, 1), prefix="futura-")

    open_voting(voting, "admin")

    assert VotingCharacterSnapshot.objects.filter(voting=voting).count() == 2


def test_abertura_sem_elegiveis_falha_sem_criar_snapshots():
    voting = VotingFactory(
        status=VotingStatus.DRAFT,
        choices_count=1,
        open_mode=Mode.MANUAL,
        catalog_cutoff_date=CUTOFF,
    )
    make_catalog(1)

    with pytest.raises(PreconditionError, match="elegíveis"):
        open_voting(voting, "admin")

    voting.refresh_from_db()
    assert voting.status == VotingStatus.DRAFT
    assert not VotingCharacterSnapshot.objects.filter(voting=voting).exists()


def test_abertura_com_catalogo_insuficiente_falha():
    voting = make_draft(choices_count=3)
    make_catalog(2)

    with pytest.raises(PreconditionError, match="catálogo"):
        open_voting(voting, "admin")


def test_abertura_manual_exige_rascunho_e_modo_manual():
    automatic = make_draft(choices_count=1, open_mode=Mode.AUTOMATIC, opens_at=future())
    make_catalog(1)
    with pytest.raises(VotingStateError):
        open_voting(automatic, "admin")

    scheduled = make_scheduled(opens_at=future(), closes_at=future(2), choices_count=1)
    with pytest.raises(VotingStateError):
        open_voting(scheduled, "admin")


def test_abertura_automatica_pelo_scheduler():
    voting = make_scheduled(opens_at=future(-1), closes_at=future(2), choices_count=2)

    opened = open_voting(voting, "scheduler")

    opened.refresh_from_db()
    assert opened.status == VotingStatus.OPEN
    assert VotingCharacterSnapshot.objects.filter(voting=opened).count() == 2


def test_scheduler_nao_abre_antes_do_horario():
    voting = make_scheduled(opens_at=future(1), closes_at=future(2), choices_count=1)

    with pytest.raises(VotingStateError, match="hora"):
        open_voting(voting, "scheduler")


def test_encerramento_bloqueia_novas_cedulas():
    voting = make_draft(choices_count=1)
    make_catalog(1)
    open_voting(voting, "admin")

    closed = close_voting(voting, "admin")

    closed.refresh_from_db()
    assert closed.status == VotingStatus.CLOSED
    assert closed.closed_at is not None

    with pytest.raises(VotingStateError):
        close_voting(closed, "admin")


def test_cancelamento_em_rascunho_e_agendada():
    draft = make_draft(choices_count=1)
    cancelled = cancel_voting(draft)
    cancelled.refresh_from_db()
    assert cancelled.status == VotingStatus.CANCELLED
    assert cancelled.cancelled_at is not None

    scheduled = make_scheduled(opens_at=future(), closes_at=future(2), choices_count=1)
    cancel_voting(scheduled)
    scheduled.refresh_from_db()
    assert scheduled.status == VotingStatus.CANCELLED


def test_cancelamento_elimina_cedulas_em_votacao_aberta():
    participant = ParticipantFactory()
    voting = make_draft(choices_count=1)
    make_catalog(1)
    open_voting(voting, "admin")
    snapshot = VotingCharacterSnapshot.objects.get(voting=voting)
    submit_ballot(voting, participant, [snapshot.pk])

    assert Ballot.objects.filter(voting=voting).count() == 1

    cancel_voting(voting, reason="teste")

    voting.refresh_from_db()
    assert voting.status == VotingStatus.CANCELLED
    assert Ballot.objects.filter(voting=voting).count() == 0


def test_cancelamento_elimina_cedulas_de_votacao_encerrada():
    participant = ParticipantFactory()
    voting = make_draft(choices_count=1)
    make_catalog(1)
    open_voting(voting, "admin")
    snapshot = VotingCharacterSnapshot.objects.get(voting=voting)
    submit_ballot(voting, participant, [snapshot.pk])
    close_voting(voting, "admin")

    cancel_voting(voting)

    assert Ballot.objects.filter(voting=voting).count() == 0


def test_cancelamento_e_idempotente():
    voting = make_draft(choices_count=1)

    first = cancel_voting(voting)
    second = cancel_voting(first)

    second.refresh_from_db()
    assert second.status == VotingStatus.CANCELLED
