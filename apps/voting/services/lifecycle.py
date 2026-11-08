"""Serviços de configuração e ciclo de vida das votações."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.catalog.services.queries import eligible_characters
from apps.core.exceptions import DomainError, PreconditionError
from apps.voting.models import (
    Mode,
    Voting,
    VotingEligibility,
    VotingStatus,
)
from apps.voting.services.eligibility import add_default_eligible

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
    """Calcula as pré-condições de abertura sem alterar a votação."""
    eligible_count = VotingEligibility.objects.filter(voting=voting).count()
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
