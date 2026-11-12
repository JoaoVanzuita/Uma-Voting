"""Serviço transacional de cédulas."""

from __future__ import annotations

import logging

from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from apps.core.exceptions import DomainError
from apps.voting.models import (
    Ballot,
    BallotChoice,
    Mode,
    Voting,
    VotingCharacterSnapshot,
    VotingEligibility,
    VotingStatus,
)

logger = logging.getLogger("apps.voting.ballots")


class BallotError(DomainError):
    pass


class InvalidBallotError(BallotError):
    pass


class VotingNotOpenError(BallotError):
    pass


class NotEligibleError(BallotError):
    pass


class AlreadyVotedError(BallotError):
    def __init__(self) -> None:
        super().__init__("Você já registrou um voto para esta votação.")


def normalize_character_ids(character_ids) -> list[int]:
    normalized: list[int] = []
    for value in character_ids:
        try:
            normalized.append(int(value))
        except (TypeError, ValueError) as exc:
            raise InvalidBallotError("A seleção de personagens é inválida.") from exc
    return normalized


def resolve_ballot_selection(voting: Voting, character_ids) -> list[VotingCharacterSnapshot]:
    """Valida quantidade, duplicidade e pertencimento ao snapshot."""
    ids = normalize_character_ids(character_ids)

    if len(ids) != len(set(ids)):
        raise InvalidBallotError("A seleção contém personagens duplicadas.")

    if len(ids) != voting.choices_count:
        raise InvalidBallotError(f"Selecione exatamente {voting.choices_count} personagens.")

    snapshots = list(VotingCharacterSnapshot.objects.filter(voting=voting, pk__in=ids))
    if len(snapshots) != len(ids):
        raise InvalidBallotError("Uma ou mais personagens não pertencem a esta votação.")

    by_id = {snapshot.pk: snapshot for snapshot in snapshots}
    return [by_id[pk] for pk in ids]


def _ensure_voting_open(voting: Voting) -> None:
    if voting.status != VotingStatus.OPEN:
        raise VotingNotOpenError("A votação não está aberta para receber votos.")

    if (
        voting.close_mode == Mode.AUTOMATIC
        and voting.closes_at is not None
        and timezone.now() >= voting.closes_at
    ):
        raise VotingNotOpenError("O prazo para votar nesta votação terminou.")


def submit_ballot(voting: Voting, participant, character_ids) -> Ballot:
    """Cria a cédula definitiva em uma transação com lock compartilhado."""
    try:
        with transaction.atomic():
            # Django não expõe FOR SHARE; o lock compartilhado permite envios
            # concorrentes e bloqueia encerramento/cancelamento (FOR UPDATE).
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT id FROM {Voting._meta.db_table} WHERE id = %s FOR SHARE",
                    [voting.pk],
                )
                if cursor.fetchone() is None:
                    raise VotingNotOpenError("A votação não está aberta para receber votos.")

            locked = Voting.objects.get(pk=voting.pk)

            _ensure_voting_open(locked)

            if not VotingEligibility.objects.filter(voting=locked, user=participant).exists():
                raise NotEligibleError("Você não é elegível para esta votação.")

            if Ballot.objects.filter(voting=locked, participant=participant).exists():
                logger.info(
                    "Tentativa de segundo envio bloqueada voting_id=%s participant_id=%s",
                    locked.pk,
                    participant.pk,
                )
                raise AlreadyVotedError()

            snapshots = resolve_ballot_selection(locked, character_ids)

            ballot = Ballot.objects.create(voting=locked, participant=participant)
            BallotChoice.objects.bulk_create(
                [BallotChoice(ballot=ballot, character_snapshot=snapshot) for snapshot in snapshots]
            )
    except IntegrityError as exc:
        logger.info(
            "Conflito de unicidade ao enviar cédula voting_id=%s participant_id=%s",
            voting.pk,
            participant.pk,
        )
        raise AlreadyVotedError() from exc

    logger.info(
        "Cédula registrada voting_id=%s participant_id=%s",
        voting.pk,
        participant.pk,
    )
    return ballot


def get_own_ballot(voting: Voting, participant) -> Ballot | None:
    """Retorna somente a cédula do próprio usuário, com suas escolhas."""
    return (
        Ballot.objects.filter(voting=voting, participant=participant)
        .prefetch_related("choices__character_snapshot__image_asset")
        .first()
    )


def delete_ballot_admin(voting: Voting, participant, admin) -> bool:
    """Exclui a cédula de um participante enquanto a votação está aberta.

    Não carrega nem registra escolhas e não mantém autoria/horário da exclusão.
    """
    with transaction.atomic():
        locked = Voting.objects.select_for_update().get(pk=voting.pk)
        _ensure_voting_open(locked)

        ballot = Ballot.objects.filter(voting=locked, participant=participant).first()
        if ballot is None:
            return False

        # A cascata de escolhas é autorizada pela flag local consumida pelas triggers.
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.ballot_delete', 'on', true)")
        ballot.delete()

    logger.info("Cédula excluída administrativamente voting_id=%s", voting.pk)
    return True
