"""Serviços de elegibilidade de votações."""

from __future__ import annotations

from django.db import transaction

from apps.accounts.models import User
from apps.core.exceptions import DomainError
from apps.voting.models import Voting, VotingEligibility, VotingStatus


class EligibilityError(DomainError):
    """Operação de elegibilidade inválida."""


def _require_draft(voting: Voting) -> None:
    if voting.status != VotingStatus.DRAFT:
        raise EligibilityError(
            "Elegíveis só podem ser alterados enquanto a votação está em rascunho."
        )


def add_default_eligible(voting: Voting) -> int:
    """Inclui todos os usuários ativos existentes, inclusive administradores.

    Usuários cadastrados depois desta chamada não são adicionados
    automaticamente. Retorna a quantidade de novas elegibilidades.
    """
    active_user_ids = list(User.objects.filter(is_active=True).values_list("id", flat=True))
    existing_user_ids = set(
        VotingEligibility.objects.filter(voting=voting).values_list("user_id", flat=True)
    )
    missing = [user_id for user_id in active_user_ids if user_id not in existing_user_ids]

    VotingEligibility.objects.bulk_create(
        [VotingEligibility(voting=voting, user_id=user_id) for user_id in missing],
        ignore_conflicts=True,
    )
    return len(missing)


def add_eligible(voting: Voting, user_ids) -> int:
    """Adiciona usuários ativos como elegíveis, somente em rascunho."""
    _require_draft(voting)
    ids = {int(getattr(user_id, "pk", user_id)) for user_id in user_ids}
    active_ids = set(
        User.objects.filter(pk__in=ids, is_active=True).values_list("id", flat=True)
    )
    existing_ids = set(
        VotingEligibility.objects.filter(voting=voting, user_id__in=active_ids).values_list(
            "user_id", flat=True
        )
    )
    missing = active_ids - existing_ids

    with transaction.atomic():
        VotingEligibility.objects.bulk_create(
            [VotingEligibility(voting=voting, user_id=user_id) for user_id in missing],
            ignore_conflicts=True,
        )
    return len(missing)


def remove_eligible(voting: Voting, user_ids) -> int:
    """Remove elegíveis, somente em rascunho."""
    _require_draft(voting)
    ids = {int(getattr(user_id, "pk", user_id)) for user_id in user_ids}
    deleted, _details = VotingEligibility.objects.filter(
        voting=voting,
        user_id__in=ids,
    ).delete()
    return deleted


def set_eligible(voting: Voting, user_ids) -> None:
    """Substitui a lista de elegíveis, somente em rascunho."""
    _require_draft(voting)
    ids = {int(getattr(user_id, "pk", user_id)) for user_id in user_ids}
    active_ids = set(
        User.objects.filter(pk__in=ids, is_active=True).values_list("id", flat=True)
    )

    with transaction.atomic():
        VotingEligibility.objects.filter(voting=voting).exclude(
            user_id__in=active_ids
        ).delete()
        existing_ids = set(
            VotingEligibility.objects.filter(voting=voting).values_list("user_id", flat=True)
        )
        VotingEligibility.objects.bulk_create(
            [
                VotingEligibility(voting=voting, user_id=user_id)
                for user_id in active_ids - existing_ids
            ],
            ignore_conflicts=True,
        )
