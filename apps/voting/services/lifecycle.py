"""Serviços de configuração e ciclo de vida das votações."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.catalog.services.queries import eligible_characters
from apps.core.exceptions import DomainError, PreconditionError
from apps.voting.models import (
    Ballot,
    Mode,
    Voting,
    VotingEligibility,
    VotingStatus,
)
from apps.voting.services.eligibility import add_default_eligible
from apps.voting.services.snapshots import create_snapshots

logger = logging.getLogger("apps.voting.lifecycle")

CONFIG_FIELDS = (
    "title",
    "description",
    "choices_count",
    "catalog_cutoff_date",
    "opens_at",
    "closes_at",
    "open_mode",
    "close_mode",
)


class VotingError(DomainError):
    """Erro de domínio em votações."""


class VotingConfigError(VotingError):
    """Configuração inválida de votação."""


class VotingStateError(VotingError):
    """Operação incompatível com o estado atual da votação."""


@dataclass(frozen=True)
class OpenPreconditions:
    eligible_count: int
    catalog_count: int
    choices_count: int
    window_open: bool

    @property
    def has_eligible(self) -> bool:
        return self.eligible_count > 0

    @property
    def has_catalog(self) -> bool:
        return self.catalog_count >= self.choices_count

    @property
    def ok(self) -> bool:
        return self.has_eligible and self.has_catalog and self.window_open

    def problems(self) -> list[str]:
        problems: list[str] = []
        if not self.has_eligible:
            problems.append("A votação não possui participantes elegíveis.")
        if not self.has_catalog:
            problems.append(
                "O catálogo não possui personagens elegíveis suficientes "
                f"para {self.choices_count} escolha(s)."
            )
        if not self.window_open:
            problems.append("A janela de encerramento já passou.")
        return problems


@dataclass(frozen=True)
class ScheduleResult:
    """Resultado de uma criação que tenta agendar na mesma ação."""

    voting: Voting
    scheduled: bool
    error: str | None = None


def validate_configuration(data: dict, *, instance: Voting | None = None) -> dict:
    """Valida a configuração comum a criação e edição."""
    cleaned = {field: data[field] for field in CONFIG_FIELDS if field in data}

    title = (cleaned.get("title") or "").strip()
    if not title:
        raise VotingConfigError("Informe o título da votação.")
    cleaned["title"] = title

    choices_count = cleaned.get("choices_count", getattr(instance, "choices_count", 3))
    try:
        choices_count = int(choices_count)
    except (TypeError, ValueError) as exc:
        raise VotingConfigError("A quantidade de escolhas deve ser um número inteiro.") from exc
    if choices_count <= 0:
        raise VotingConfigError("A quantidade de escolhas deve ser maior que zero.")
    cleaned["choices_count"] = choices_count

    open_mode = cleaned.get("open_mode", getattr(instance, "open_mode", Mode.MANUAL))
    close_mode = cleaned.get("close_mode", getattr(instance, "close_mode", Mode.MANUAL))
    if open_mode not in Mode.values:
        raise VotingConfigError("Modo de abertura inválido.")
    if close_mode not in Mode.values:
        raise VotingConfigError("Modo de encerramento inválido.")
    cleaned["open_mode"] = open_mode
    cleaned["close_mode"] = close_mode

    opens_at = cleaned.get("opens_at", getattr(instance, "opens_at", None))
    closes_at = cleaned.get("closes_at", getattr(instance, "closes_at", None))

    if open_mode == Mode.AUTOMATIC and opens_at is None:
        raise VotingConfigError("A data de abertura é obrigatória no modo automático.")
    if close_mode == Mode.AUTOMATIC and closes_at is None:
        raise VotingConfigError("A data de encerramento é obrigatória no modo automático.")
    # Apenas na criação: rascunhos antigos com abertura vencida continuam editáveis.
    if (
        instance is None
        and open_mode == Mode.AUTOMATIC
        and opens_at is not None
        and opens_at <= timezone.now()
    ):
        raise VotingConfigError("A data de abertura deve estar no futuro.")
    if opens_at and closes_at and closes_at <= opens_at:
        raise VotingConfigError("O encerramento deve ser posterior à abertura.")

    cleaned["opens_at"] = opens_at
    cleaned["closes_at"] = closes_at
    return cleaned


def create_voting(data: dict, admin) -> Voting:
    """Cria uma votação em rascunho com todos os usuários ativos elegíveis."""
    cleaned = validate_configuration(data)

    with transaction.atomic():
        voting = Voting.objects.create(
            **cleaned,
            status=VotingStatus.DRAFT,
            created_by=admin,
        )
        add_default_eligible(voting)

    logger.info("Votação criada voting_id=%s admin_id=%s", voting.pk, admin.pk)
    return voting


def create_and_schedule_voting(data: dict, admin) -> ScheduleResult:
    """Cria a votação e tenta agendar na mesma ação, sem desfazer o rascunho.

    Uma falha de pré-condição reverte apenas o savepoint do agendamento; o motivo é
    devolvido no resultado em vez de lançado, porque uma exceção fora do savepoint
    faria o `atomic()` externo descartar a votação recém-criada.
    """
    with transaction.atomic():
        voting = create_voting(data, admin)
        try:
            with transaction.atomic():
                scheduled = schedule_voting(voting)
        except (VotingConfigError, PreconditionError) as exc:
            logger.info(
                "Votação criada com agendamento bloqueado voting_id=%s motivo=%s",
                voting.pk,
                exc.message,
            )
            return ScheduleResult(voting=voting, scheduled=False, error=exc.message)

    logger.info("Votação criada e agendada voting_id=%s", scheduled.pk)
    return ScheduleResult(voting=scheduled, scheduled=True)


def update_voting(voting: Voting, data: dict) -> Voting:
    """Atualiza a configuração de uma votação em rascunho."""
    with transaction.atomic():
        locked = Voting.objects.select_for_update().get(pk=voting.pk)
        if locked.status != VotingStatus.DRAFT:
            raise VotingStateError("Somente votações em rascunho podem ser editadas.")

        cleaned = validate_configuration(data, instance=locked)
        for field, value in cleaned.items():
            setattr(locked, field, value)
        locked.save(update_fields=[*cleaned.keys(), "updated_at"])

    logger.info("Votação atualizada voting_id=%s", voting.pk)
    return locked


def evaluate_open_preconditions(voting: Voting) -> OpenPreconditions:
    """Calcula as pré-condições de abertura sem alterar a votação.

    Uma instância ainda não salva tem zero elegíveis por definição, o que permite
    avaliar a configuração de criação antes do `INSERT`.
    """
    eligible_count = (
        0 if voting.pk is None else VotingEligibility.objects.filter(voting=voting).count()
    )
    catalog_count = eligible_characters(voting.catalog_cutoff_date).count()
    window_open = True
    if voting.close_mode == Mode.AUTOMATIC and voting.closes_at is not None:
        window_open = voting.closes_at > timezone.now()
    return OpenPreconditions(
        eligible_count=eligible_count,
        catalog_count=catalog_count,
        choices_count=voting.choices_count,
        window_open=window_open,
    )


def check_open_preconditions(voting: Voting) -> OpenPreconditions:
    """Garante que a votação pode ser aberta; lança ``PreconditionError``."""
    preconditions = evaluate_open_preconditions(voting)
    if not preconditions.ok:
        raise PreconditionError(" ".join(preconditions.problems()))
    return preconditions


def schedule_voting(voting: Voting) -> Voting:
    """Agenda uma votação automática, congelando a configuração."""
    with transaction.atomic():
        locked = Voting.objects.select_for_update().get(pk=voting.pk)
        if locked.status != VotingStatus.DRAFT:
            raise VotingStateError("Somente votações em rascunho podem ser agendadas.")
        if locked.open_mode != Mode.AUTOMATIC:
            raise VotingConfigError("A abertura automática exige o modo automático.")
        if locked.opens_at is None:
            raise VotingConfigError("A data de abertura é obrigatória no modo automático.")
        if locked.opens_at <= timezone.now():
            raise VotingConfigError("A data de abertura deve estar no futuro.")
        if locked.closes_at is not None and locked.closes_at <= locked.opens_at:
            raise VotingConfigError("O encerramento deve ser posterior à abertura.")

        check_open_preconditions(locked)

        locked.status = VotingStatus.SCHEDULED
        locked.save(update_fields=["status", "updated_at"])

    logger.info("Votação agendada voting_id=%s", voting.pk)
    return locked


def open_voting(voting: Voting, trigger: str) -> Voting:
    """Abre a votação, congela elegíveis/catálogo e cria os snapshots.

    ``trigger`` é ``admin`` para abertura manual em rascunho ou ``scheduler``
    para a abertura automática de uma votação agendada.
    """
    now = timezone.now()

    with transaction.atomic():
        locked = Voting.objects.select_for_update().get(pk=voting.pk)

        if trigger == "admin":
            if locked.status != VotingStatus.DRAFT:
                raise VotingStateError(
                    "Somente votações em rascunho podem ser abertas manualmente."
                )
            if locked.open_mode != Mode.MANUAL:
                raise VotingStateError(
                    "Votações com abertura automática são abertas pelo agendador."
                )
        elif trigger == "scheduler":
            if locked.status != VotingStatus.SCHEDULED:
                raise VotingStateError(
                    "Somente votações agendadas podem ser abertas pelo agendador."
                )
            if locked.open_mode != Mode.AUTOMATIC:
                raise VotingStateError("A votação não está configurada para abertura automática.")
            if locked.opens_at is None or locked.opens_at > now:
                raise VotingStateError("Ainda não é hora de abrir esta votação.")
        else:
            raise VotingStateError("Gatilho de abertura inválido.")

        check_open_preconditions(locked)
        create_snapshots(locked)

        locked.eligible_frozen_at = now
        locked.catalog_frozen_at = now
        locked.opened_at = now
        locked.status = VotingStatus.OPEN
        locked.save(
            update_fields=[
                "eligible_frozen_at",
                "catalog_frozen_at",
                "opened_at",
                "status",
                "updated_at",
            ]
        )

    logger.info("Votação aberta voting_id=%s trigger=%s", voting.pk, trigger)
    return locked


def close_voting(voting: Voting, trigger: str = "admin") -> Voting:
    """Encerra uma votação aberta, bloqueando novas cédulas."""
    with transaction.atomic():
        locked = Voting.objects.select_for_update().get(pk=voting.pk)
        if locked.status != VotingStatus.OPEN:
            raise VotingStateError("Somente votações abertas podem ser encerradas.")

        locked.closed_at = timezone.now()
        locked.status = VotingStatus.CLOSED
        locked.save(update_fields=["closed_at", "status", "updated_at"])

    logger.info("Votação encerrada voting_id=%s trigger=%s", voting.pk, trigger)
    return locked


def cancel_voting(voting: Voting, admin=None, reason: str | None = None) -> Voting:
    """Cancela a votação em qualquer estado e elimina todas as cédulas.

    O status é alterado para ``cancelled`` antes da exclusão das cédulas para
    satisfazer as triggers de janela de exclusão. A operação é idempotente.
    """
    with transaction.atomic():
        locked = Voting.objects.select_for_update().get(pk=voting.pk)
        if locked.status == VotingStatus.CANCELLED:
            return locked

        locked.status = VotingStatus.CANCELLED
        locked.cancelled_at = timezone.now()
        locked.save(update_fields=["status", "cancelled_at", "updated_at"])

        # As triggers permitem a exclusão com a votação já cancelada.
        Ballot.objects.filter(voting=locked).delete()

    logger.info(
        "Votação cancelada voting_id=%s admin_id=%s reason=%s",
        voting.pk,
        getattr(admin, "pk", None),
        reason or "-",
    )
    return locked
