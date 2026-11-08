"""Testes das triggers PostgreSQL de cédulas e escolhas."""

from datetime import timedelta

import pytest
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.voting.models import (
    Ballot,
    BallotChoice,
    Mode,
    Voting,
    VotingStatus,
)
from apps.voting.tests.helpers import create_candidate, create_open_voting
from tests.factories import (
    BallotFactory,
    OpenVotingFactory,
    ParticipantFactory,
    VotingEligibilityFactory,
    VotingFactory,
)


def _raw_delete_ballot(pk: int) -> None:
    """Exclui a cédula diretamente, para validar a trigger de janela."""
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM voting_ballot WHERE id = %s", [pk])


def _admin_delete_ballot(ballot) -> None:
    """Simula a exclusão administrativa: flag local, escolhas e cédula."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.ballot_delete', 'on', true)")
        BallotChoice.objects.filter(ballot_id=ballot.pk).delete()
        Ballot.objects.filter(pk=ballot.pk).delete()


@pytest.mark.django_db
def test_cedula_so_pode_ser_inserida_com_votacao_aberta():
    voting = VotingFactory(status=VotingStatus.DRAFT)
    participant = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=participant)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Ballot.objects.create(voting=voting, participant=participant)


@pytest.mark.django_db
def test_cedula_exige_participante_elegivel():
    voting = OpenVotingFactory()
    participant = ParticipantFactory()

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Ballot.objects.create(voting=voting, participant=participant)


@pytest.mark.django_db
def test_cedula_bloqueada_quando_prazo_automatico_passou():
    voting = OpenVotingFactory(
        close_mode=Mode.AUTOMATIC,
        closes_at=timezone.now() - timedelta(minutes=1),
    )
    participant = ParticipantFactory()
    VotingEligibilityFactory(voting=voting, user=participant)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Ballot.objects.create(voting=voting, participant=participant)


@pytest.mark.django_db
def test_cedula_nao_pode_ser_alterada():
    ballot = BallotFactory()
    other = ParticipantFactory()
    VotingEligibilityFactory(voting=ballot.voting, user=other)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Ballot.objects.filter(pk=ballot.pk).update(participant=other)


@pytest.mark.django_db
def test_exclusao_de_cedula_com_votacao_aberta_e_permitida():
    ballot = BallotFactory()

    _admin_delete_ballot(ballot)

    assert Ballot.objects.filter(pk=ballot.pk).exists() is False
    assert BallotChoice.objects.filter(ballot_id=ballot.pk).count() == 0


@pytest.mark.django_db
def test_exclusao_de_cedula_com_votacao_encerrada_e_bloqueada():
    ballot = BallotFactory()
    Voting.objects.filter(pk=ballot.voting_id).update(status=VotingStatus.CLOSED)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            _raw_delete_ballot(ballot.pk)


@pytest.mark.django_db
def test_escolha_precisa_pertencer_a_votacao_da_cedula():
    ballot = BallotFactory()
    other_voting = OpenVotingFactory()
    foreign_snapshot = create_candidate(other_voting, "Personagem Externa")

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            BallotChoice.objects.create(ballot=ballot, character_snapshot=foreign_snapshot)


@pytest.mark.django_db
def test_escolha_nao_pode_ser_alterada():
    ballot = BallotFactory()
    choice = ballot.choices.first()

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            BallotChoice.objects.filter(pk=choice.pk).update(
                character_snapshot=choice.character_snapshot_id
            )


@pytest.mark.django_db
def test_exclusao_individual_de_escolha_e_bloqueada():
    ballot = BallotFactory()
    choice = ballot.choices.first()

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            choice.delete()


@pytest.mark.django_db
def test_exclusao_administrativa_remove_escolhas_com_flag():
    ballot = BallotFactory()

    _admin_delete_ballot(ballot)

    assert BallotChoice.objects.filter(ballot_id=ballot.pk).count() == 0
    assert Ballot.objects.filter(pk=ballot.pk).exists() is False


@pytest.mark.django_db(transaction=True)
def test_contagem_exata_de_escolhas_e_aceita_no_commit():
    voting, participant, snapshots = create_open_voting(choices_count=3)

    with transaction.atomic():
        ballot = Ballot.objects.create(voting=voting, participant=participant)
        BallotChoice.objects.bulk_create(
            [BallotChoice(ballot=ballot, character_snapshot=snapshot) for snapshot in snapshots[:3]]
        )

    assert Ballot.objects.filter(pk=ballot.pk).exists()
    assert BallotChoice.objects.filter(ballot=ballot).count() == 3


@pytest.mark.django_db(transaction=True)
def test_contagem_incorreta_bloqueia_o_commit():
    voting, participant, snapshots = create_open_voting(choices_count=3)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            ballot = Ballot.objects.create(voting=voting, participant=participant)
            BallotChoice.objects.bulk_create(
                [
                    BallotChoice(ballot=ballot, character_snapshot=snapshot)
                    for snapshot in snapshots[:2]
                ]
            )

    assert Ballot.objects.filter(voting=voting, participant=participant).count() == 0


# ---------------------------------------------------------------------------
# Triggers de ciclo de vida, configuração e snapshots (Fase 8)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_transicao_de_estado_invalida_e_rejeitada():
    voting = VotingFactory(status=VotingStatus.DRAFT)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Voting.objects.filter(pk=voting.pk).update(status=VotingStatus.CLOSED)


@pytest.mark.django_db
def test_configuracao_imutavel_apos_agendamento():
    voting = VotingFactory(status=VotingStatus.SCHEDULED)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            Voting.objects.filter(pk=voting.pk).update(title="Título alterado")


@pytest.mark.django_db
def test_elegibilidade_bloqueada_fora_do_rascunho():
    voting = OpenVotingFactory()
    participant = ParticipantFactory()

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            from apps.voting.models import VotingEligibility

            VotingEligibility.objects.create(voting=voting, user=participant)


@pytest.mark.django_db
def test_snapshot_bloqueado_em_votacao_ja_aberta():
    from apps.voting.models import VotingCharacterSnapshot
    from tests.factories import CharacterFactory

    voting = OpenVotingFactory()
    character = CharacterFactory()

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            VotingCharacterSnapshot.objects.create(
                voting=voting,
                source_character=character,
                stable_id=character.stable_id,
                display_name=character.display_name,
            )


@pytest.mark.django_db
def test_snapshot_nao_pode_ser_alterado_nem_apagado():
    from apps.voting.models import VotingCharacterSnapshot
    from tests.factories import VotingCharacterSnapshotFactory

    snapshot = VotingCharacterSnapshotFactory()

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            VotingCharacterSnapshot.objects.filter(pk=snapshot.pk).update(
                display_name="Alterado"
            )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            snapshot.delete()


@pytest.mark.django_db
def test_imagem_do_snapshot_deve_pertencer_a_personagem():
    from apps.voting.models import VotingCharacterSnapshot
    from tests.factories import CharacterFactory, ImageAssetFactory

    voting = VotingFactory(status=VotingStatus.DRAFT)
    character = CharacterFactory()
    other = CharacterFactory()
    image = ImageAssetFactory(character=other)

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            VotingCharacterSnapshot.objects.create(
                voting=voting,
                source_character=character,
                stable_id=character.stable_id,
                display_name=character.display_name,
                image_asset=image,
            )


@pytest.mark.django_db
def test_versao_do_snapshot_deve_pertencer_a_personagem():
    from apps.voting.models import VotingCharacterSnapshot, VotingVersionSnapshot
    from tests.factories import CharacterFactory, CharacterVersionFactory

    voting = VotingFactory(status=VotingStatus.DRAFT)
    character = CharacterFactory()
    other = CharacterFactory()
    version = CharacterVersionFactory(character=other)

    with transaction.atomic():
        snapshot = VotingCharacterSnapshot.objects.create(
            voting=voting,
            source_character=character,
            stable_id=character.stable_id,
            display_name=character.display_name,
        )

    with pytest.raises(DatabaseError):
        with transaction.atomic():
            VotingVersionSnapshot.objects.create(
                character_snapshot=snapshot,
                source_version=version,
                stable_id=version.stable_id,
                release_date_global=version.release_date_global or timezone.now().date(),
            )
