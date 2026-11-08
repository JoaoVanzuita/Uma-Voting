"""Agregação de resultados e participação, sem expor escolhas individuais."""

from __future__ import annotations

from dataclasses import dataclass

from django.db.models import Count, Exists, OuterRef

from apps.catalog.models import ImageAsset
from apps.voting.models import (
    Ballot,
    Voting,
    VotingCharacterSnapshot,
    VotingEligibility,
    VotingStatus,
)


@dataclass(frozen=True)
class ResultRow:
    stable_id: str
    display_name: str
    image_asset: ImageAsset | None
    votes: int


@dataclass(frozen=True)
class RankedResultRow:
    position: int
    stable_id: str
    display_name: str
    image_asset: ImageAsset | None
    votes: int


@dataclass(frozen=True)
class ParticipationRow:
    username: str
    voted: bool


def aggregate_results(voting: Voting) -> list[ResultRow]:
    """Agrega votos por personagem do snapshot; nunca retorna participantes."""
    if voting.status == VotingStatus.CANCELLED:
        return []

    rows = (
        VotingCharacterSnapshot.objects.filter(voting=voting)
        .select_related("image_asset")
        .annotate(votes=Count("ballot_choices"))
        .order_by("-votes", "display_name")
    )
    return [
        ResultRow(
            stable_id=row.stable_id,
            display_name=row.display_name,
            image_asset=row.image_asset,
            votes=row.votes,
        )
        for row in rows
    ]


def rank_results(rows: list[ResultRow]) -> list[RankedResultRow]:
    """Aplica dense rank a personagens com ao menos um voto.

    Nomes são usados apenas para ordenação estável de apresentação, nunca como
    critério de desempate de posição.
    """
    ordered = sorted(
        (row for row in rows if row.votes > 0),
        key=lambda row: (-row.votes, row.display_name),
    )

    ranked: list[RankedResultRow] = []
    position = 0
    previous_votes: int | None = None

    for row in ordered:
        if row.votes != previous_votes:
            position += 1
            previous_votes = row.votes
        ranked.append(
            RankedResultRow(
                position=position,
                stable_id=row.stable_id,
                display_name=row.display_name,
                image_asset=row.image_asset,
                votes=row.votes,
            )
        )
    return ranked


def final_results(voting: Voting) -> list[RankedResultRow]:
    return rank_results(aggregate_results(voting))


def participation(voting: Voting) -> list[ParticipationRow]:
    """Lista elegíveis e se votaram, sem qualquer escolha individual."""
    ballots = Ballot.objects.filter(voting=voting)
    rows = (
        VotingEligibility.objects.filter(voting=voting)
        .select_related("user")
        .annotate(
            voted=Exists(ballots.filter(participant_id=OuterRef("user_id")))
        )
        .order_by("user__username")
    )
    return [
        ParticipationRow(username=row.user.username, voted=row.voted)
        for row in rows
    ]
