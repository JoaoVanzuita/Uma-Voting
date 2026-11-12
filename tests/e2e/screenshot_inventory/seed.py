"""Prepara o banco isolado usado pelo inventário visual de telas.

Executado com ``python manage.py shell < tests/e2e/screenshot_inventory/seed.py``
dentro do container de screenshots. O banco é um clone descartável do banco
local; nenhum registro do banco principal é tocado.

O script é idempotente: remove os registros com prefixo ``[SCREENSHOT]`` e
recria os cenários determinísticos usados pelo Playwright.
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, time
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.utils import timezone

from apps.catalog.models import (
    Aptitude,
    CatalogSource,
    Character,
    CharacterVersion,
    CharacterVersionAptitude,
    ImageAsset,
    SyncChange,
    SyncRun,
)
from apps.voting.models import (
    Ballot,
    BallotChoice,
    Voting,
    VotingCharacterSnapshot,
    VotingEligibility,
)
from apps.voting.services.ballots import submit_ballot
from apps.voting.services.eligibility import add_default_eligible
from apps.voting.services.lifecycle import cancel_voting, close_voting, open_voting, schedule_voting

User = get_user_model()

PREFIX = "[SCREENSHOT]"
OUTPUT_DIR = Path(settings.BASE_DIR) / "var" / "screenshots"
FIXTURE_DIR = OUTPUT_DIR / "fixtures"
SCENARIO_FILE = OUTPUT_DIR / "scenario.json"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "TesteLocal!2026"
PARTICIPANT_USERNAME = "Teste"
EMPTY_USERNAME = "screenshot_empty"

CUTOFF = date(2026, 12, 1)
SOURCE_NAME = "curadoria-local"


def _disable_triggers(cursor) -> None:
    cursor.execute("SET LOCAL session_replication_role = replica")


def _purge_previous_scenarios() -> None:
    """Remove cenários anteriores sem esbarrar nas triggers de imutabilidade."""
    # Mudanças de sincronização criadas a partir do personagem de teste.
    scenario_changes = SyncChange.objects.filter(
        character__stable_id__startswith="screenshot-"
    ) | SyncChange.objects.filter(version__character__stable_id__startswith="screenshot-")
    sync_run_ids = set(scenario_changes.values_list("sync_run_id", flat=True))
    if scenario_changes.exists():
        scenario_changes.delete()
    for run_id in sync_run_ids:
        run = SyncRun.objects.filter(pk=run_id).first()
        if run is not None and not run.changes.exists():
            run.delete()
    # Execuções de falha não geram SyncChange e não têm referências protegidas.
    SyncRun.objects.filter(source__name=SOURCE_NAME, changes__isnull=True).delete()

    votings = Voting.objects.filter(title__startswith=PREFIX)
    if votings.exists():
        with transaction.atomic():
            with connection.cursor() as cursor:
                _disable_triggers(cursor)
            ballots = Ballot.objects.filter(voting__in=votings)
            BallotChoice.objects.filter(ballot__in=ballots).delete()
            ballots.delete()
            VotingEligibility.objects.filter(voting__in=votings).delete()
            # CASCADE remove versões e aptidões dos snapshots.
            VotingCharacterSnapshot.objects.filter(voting__in=votings).delete()
            votings.delete()

    users = User.objects.filter(username__startswith="screenshot_")
    if users.exists():
        with transaction.atomic():
            with connection.cursor() as cursor:
                _disable_triggers(cursor)
            Ballot.objects.filter(participant__in=users).delete()
            VotingEligibility.objects.filter(user__in=users).delete()
            users.delete()

    characters = Character.objects.filter(stable_id__startswith="screenshot-")
    if characters.exists():
        with transaction.atomic():
            with connection.cursor() as cursor:
                _disable_triggers(cursor)
            CharacterVersion.objects.filter(character__in=characters).delete()
            ImageAsset.objects.filter(character__in=characters).delete()
            characters.delete()

    for filename in ("screenshot-invalid.bin", "screenshot-missing.png"):
        (Path(settings.MEDIA_ROOT) / filename).unlink(missing_ok=True)


def _ensure_users() -> tuple[User, User]:
    admin, _ = User.objects.get_or_create(
        username=ADMIN_USERNAME,
        defaults={"is_admin": True, "is_active": True, "is_staff": True},
    )
    admin.is_admin = True
    admin.is_active = True
    admin.is_staff = True
    admin.set_password(ADMIN_PASSWORD)
    admin.save()

    participant, _ = User.objects.get_or_create(
        username=PARTICIPANT_USERNAME,
        defaults={"is_admin": False, "is_active": True},
    )
    participant.is_admin = False
    participant.is_active = True
    participant.set_unusable_password()
    participant.save()
    return admin, participant


def _aptitude(category: str, value: str) -> Aptitude:
    return Aptitude.objects.get(category=category, value=value)


def _create_version(character: Character, stable_id: str, name: str) -> CharacterVersion:
    source = CatalogSource.objects.filter(name=SOURCE_NAME).first()
    version, _ = CharacterVersion.objects.update_or_create(
        stable_id=stable_id,
        defaults={
            "character": character,
            "display_name": name,
            "release_date_global": date(2025, 1, 1),
            "source": source,
        },
    )
    for category, value in (
        ("strategy", "pace"),
        ("distance", "mile"),
        ("surface", "turf"),
    ):
        CharacterVersionAptitude.objects.get_or_create(
            version=version,
            aptitude=_aptitude(category, value),
        )
    return version


def _create_scenario_characters() -> dict[str, int]:
    source = CatalogSource.objects.filter(name=SOURCE_NAME).first()
    objects = {}

    no_image, _ = Character.objects.update_or_create(
        stable_id="screenshot-sem-imagem",
        defaults={"display_name": "Screenshot Sem Imagem"},
    )
    _create_version(no_image, "screenshot-sem-imagem-v1", "Screenshot Sem Imagem (Original)")
    objects["no_image"] = no_image.pk

    invalid, _ = Character.objects.update_or_create(
        stable_id="screenshot-imagem-invalida",
        defaults={"display_name": "Screenshot Imagem Inválida"},
    )
    _create_version(
        invalid,
        "screenshot-imagem-invalida-v1",
        "Screenshot Imagem Inválida (Original)",
    )
    ImageAsset.objects.update_or_create(
        file_path="screenshot-invalid.bin",
        defaults={
            "character": invalid,
            "is_current": True,
            "status": ImageAsset.Status.INVALID,
            "width": 256,
            "height": 256,
            "source": source,
        },
    )
    (Path(settings.MEDIA_ROOT) / "screenshot-invalid.bin").write_bytes(
        b"arquivo de teste que nao e uma imagem"
    )
    objects["invalid"] = invalid.pk

    missing, _ = Character.objects.update_or_create(
        stable_id="screenshot-imagem-ausente",
        defaults={"display_name": "Screenshot Imagem Ausente"},
    )
    _create_version(missing, "screenshot-imagem-ausente-v1", "Screenshot Imagem Ausente (Original)")
    ImageAsset.objects.update_or_create(
        file_path="screenshot-missing.png",
        defaults={
            "character": missing,
            "is_current": True,
            "status": ImageAsset.Status.MISSING,
            "width": 256,
            "height": 256,
            "source": source,
        },
    )
    objects["missing"] = missing.pk

    sync_character, _ = Character.objects.update_or_create(
        stable_id="screenshot-sync",
        defaults={"display_name": "Screenshot Sincronização"},
    )
    _create_version(sync_character, "screenshot-sync-v1", "Screenshot Sincronização (Original)")
    objects["sync"] = sync_character.pk

    return objects


def _new_voting(
    admin: User,
    *,
    title: str,
    choices: int = 3,
    cutoff: date = CUTOFF,
    **kwargs,
) -> Voting:
    voting = Voting.objects.create(
        title=f"{PREFIX} {title}",
        description=(
            "Cenário criado automaticamente para o inventário visual de telas. "
            "Não faz parte dos dados funcionais da aplicação."
        ),
        choices_count=choices,
        catalog_cutoff_date=cutoff,
        status="draft",
        created_by=admin,
        **kwargs,
    )
    add_default_eligible(voting)
    return voting


def _build_votings(admin: User, participant: User) -> dict[str, dict]:
    votings: dict[str, dict] = {}

    # 1. Votação aberta usada no fluxo completo do participante.
    open_voting_obj = _new_voting(admin, title="Votação aberta — fluxo completo")
    open_voting_obj = open_voting(open_voting_obj, "admin")
    votings["open"] = {
        "id": open_voting_obj.pk,
        "title": open_voting_obj.title,
        "status": open_voting_obj.status,
    }

    # 2. Votação aberta com cédulas (para detalhe, resultados e participação).
    open_ballots = _new_voting(admin, title="Aberta com cédulas")
    open_ballots = open_voting(open_ballots, "admin")
    open_snapshots = list(open_ballots.character_snapshots.order_by("display_name")[:4])
    if len(open_snapshots) >= 4:
        submit_ballot(
            open_ballots,
            participant,
            [open_snapshots[0].pk, open_snapshots[1].pk, open_snapshots[2].pk],
        )
        submit_ballot(
            open_ballots,
            admin,
            [open_snapshots[0].pk, open_snapshots[1].pk, open_snapshots[3].pk],
        )
    votings["open_ballots"] = {
        "id": open_ballots.pk,
        "title": open_ballots.title,
        "status": open_ballots.status,
    }

    # 3. Votação encerrada com cédulas e empate no ranking.
    closed = _new_voting(admin, title="Votação encerrada — com ranking")
    closed = open_voting(closed, "admin")
    snapshots = list(closed.character_snapshots.order_by("display_name")[:4])
    if len(snapshots) >= 4:
        submit_ballot(closed, participant, [snapshots[0].pk, snapshots[1].pk, snapshots[2].pk])
        submit_ballot(closed, admin, [snapshots[0].pk, snapshots[1].pk, snapshots[3].pk])
    closed = close_voting(closed, "admin")
    votings["closed"] = {
        "id": closed.pk,
        "title": closed.title,
        "status": closed.status,
    }

    # 3. Votação encerrada sem cédulas (estado vazio de resultado).
    closed_empty = _new_voting(admin, title="Encerrada sem resposta")
    closed_empty = open_voting(closed_empty, "admin")
    closed_empty = close_voting(closed_empty, "admin")
    votings["closed_no_ballot"] = {
        "id": closed_empty.pk,
        "title": closed_empty.title,
        "status": closed_empty.status,
    }

    # 4. Rascunho pronto para abrir.
    draft = _new_voting(admin, title="Rascunho — pronto para abrir")
    votings["draft"] = {
        "id": draft.pk,
        "title": draft.title,
        "status": draft.status,
    }

    # 5. Rascunho com pré-condições pendentes (sem elegíveis e catálogo insuficiente).
    draft_blocked = _new_voting(admin, title="Rascunho — pré-condições pendentes", choices=999)
    VotingEligibility.objects.filter(voting=draft_blocked).delete()
    votings["draft_blocked"] = {
        "id": draft_blocked.pk,
        "title": draft_blocked.title,
        "status": draft_blocked.status,
    }

    # 6. Votação agendada (abertura automática futura).
    opens_at = timezone.make_aware(datetime.combine(date(2030, 1, 15), time(10, 0)))
    closes_at = timezone.make_aware(datetime.combine(date(2030, 1, 20), time(18, 0)))
    scheduled = _new_voting(
        admin,
        title="Agendada — abertura automática",
        open_mode="automatic",
        close_mode="automatic",
        opens_at=opens_at,
        closes_at=closes_at,
    )
    scheduled = schedule_voting(scheduled)
    votings["scheduled"] = {
        "id": scheduled.pk,
        "title": scheduled.title,
        "status": scheduled.status,
    }

    # 7. Votação cancelada (cédulas eliminadas).
    cancelled = _new_voting(admin, title="Cancelada — histórico")
    cancelled = open_voting(cancelled, "admin")
    cancelled_snapshots = list(cancelled.character_snapshots.order_by("display_name")[:3])
    if len(cancelled_snapshots) == 3:
        submit_ballot(cancelled, participant, [row.pk for row in cancelled_snapshots])
    cancelled = cancel_voting(cancelled, admin, "Cenário de inventário visual")
    votings["cancelled"] = {
        "id": cancelled.pk,
        "title": cancelled.title,
        "status": cancelled.status,
    }

    # 8. Votação aberta usada para o conflito de encerramento (P08).
    unavailable = _new_voting(admin, title="Fluxo de indisponibilidade")
    unavailable = open_voting(unavailable, "admin")
    votings["unavailable"] = {
        "id": unavailable.pk,
        "title": unavailable.title,
        "status": unavailable.status,
    }

    return votings


def _write_fixtures() -> None:
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "participant-import-invalid.csv").write_text(
        "username\nTeste\nscreenshot_import_ok\nscreenshot_import_ok\nBad,Name\n",
        encoding="utf-8",
    )
    (FIXTURE_DIR / "participant-import-valid.csv").write_text(
        "username\nscreenshot_import_ana\nscreenshot_import_bia\n",
        encoding="utf-8",
    )
    (FIXTURE_DIR / "catalog-sync-invalid.csv").write_text(
        "character_stable_id,character_name,version_stable_id,version_name,"
        "release_date_global,strategy,distances,surfaces\n"
        "screenshot-sync,Screenshot Sincronização,screenshot-sync-v1,"
        "Screenshot Sincronização v1,2025-01-01,invalid-strategy,mile,turf\n",
        encoding="utf-8",
    )
    (FIXTURE_DIR / "catalog-sync-pending.csv").write_text(
        "character_stable_id,character_name,version_stable_id,version_name,"
        "release_date_global,strategy,distances,surfaces\n"
        "screenshot-sync,Screenshot Sincronização (atualizada),screenshot-sync-v1,"
        "Screenshot Sincronização v1 (atualizada),2025-01-02,late,mile;long,turf;dirt\n",
        encoding="utf-8",
    )


def main() -> None:
    database_name = str(settings.DATABASES["default"]["NAME"])
    if not database_name.endswith("_screens") and os.environ.get("ALLOW_SCREENSHOT_SEED") != "1":
        raise SystemExit(
            "Recusando alterar um banco que não termina em '_screens'. "
            "Use o banco isolado criado por run.sh ou defina ALLOW_SCREENSHOT_SEED=1."
        )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _purge_previous_scenarios()
    _write_fixtures()

    admin, participant = _ensure_users()
    characters = _create_scenario_characters()
    votings = _build_votings(admin, participant)

    # Criado depois das votações para não herdar elegibilidade em nenhum cenário.
    empty_user, _ = User.objects.get_or_create(
        username=EMPTY_USERNAME,
        defaults={"is_admin": False, "is_active": True},
    )
    empty_user.is_active = True
    empty_user.is_admin = False
    empty_user.set_unusable_password()
    empty_user.save()

    # HTML fiel do template 500 para o Playwright renderizar via interceptação,
    # já que não existe rota pública que provoque um erro interno controlado.
    request = RequestFactory().get("/")
    (OUTPUT_DIR / "500.html").write_text(
        render_to_string("errors/500.html", request=request),
        encoding="utf-8",
    )

    scenario = {
        "generated_at": timezone.now().isoformat(),
        "credentials": {
            "admin": {"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
            "participant": {"username": PARTICIPANT_USERNAME},
            "empty_participant": {"username": EMPTY_USERNAME},
        },
        "users": {
            "admin_id": admin.pk,
            "participant_id": participant.pk,
            "empty_participant_id": empty_user.pk,
        },
        "votings": votings,
        "characters": characters,
        "fixtures": {
            "participant_import_invalid": str(FIXTURE_DIR / "participant-import-invalid.csv"),
            "participant_import_valid": str(FIXTURE_DIR / "participant-import-valid.csv"),
            "catalog_sync_invalid": str(FIXTURE_DIR / "catalog-sync-invalid.csv"),
            "catalog_sync_pending": str(FIXTURE_DIR / "catalog-sync-pending.csv"),
        },
        "counts": {
            "characters": Character.objects.count(),
            "images": ImageAsset.objects.count(),
            "votings": Voting.objects.count(),
        },
    }
    SCENARIO_FILE.write_text(
        json.dumps(scenario, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("Cenário de screenshots preparado:")
    for key, value in votings.items():
        print(f"  {key:16s} id={value['id']:<4} status={value['status']}")
    print(f"  personagens extras: {characters}")
    print(f"  saída: {SCENARIO_FILE}")


main()
