"""Serviços de elegibilidade de votações."""

from __future__ import annotations

from apps.accounts.models import User
from apps.voting.models import Voting, VotingEligibility


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
