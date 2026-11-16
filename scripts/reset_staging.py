"""Limpa votações e catálogo do staging, preservando usuários e fontes.

Uso:
    DJANGO_SETTINGS_MODULE=config.settings.staging \
        python manage.py shell < scripts/reset_staging.py

Depois remova os arquivos órfãos de mídia:
    rm -rf media/characters

As triggers de votações protegem cédulas, snapshots e execuções de importação.
Para uma limpeza operacional, as triggers são desativadas apenas dentro desta
transação e reativadas ao final; qualquer erro desfaz tudo.
"""

from django.db import connection, transaction

from apps.catalog.models import (
    CatalogSource,
    Character,
    CharacterVersion,
    ImageAsset,
    ImportJob,
    SyncChange,
    SyncRun,
)
from apps.voting.models import (
    Ballot,
    BallotChoice,
    Voting,
    VotingCharacterSnapshot,
    VotingEligibility,
    VotingVersionAptitudeSnapshot,
    VotingVersionSnapshot,
)

TRIGGER_TABLES = [
    "voting_ballotchoice",
    "voting_ballot",
    "voting_votingeligibility",
    "voting_votingversionaptitudesnapshot",
    "voting_votingversionsnapshot",
    "voting_votingcharactersnapshot",
    "voting_voting",
    "catalog_importjob",
]

counts: dict[str, int] = {}

with transaction.atomic():
    with connection.cursor() as cursor:
        for table in TRIGGER_TABLES:
            cursor.execute(f"ALTER TABLE {table} DISABLE TRIGGER USER")

    counts["choices"] = BallotChoice.objects.all().delete()[0]
    counts["ballots"] = Ballot.objects.all().delete()[0]
    counts["eligibility"] = VotingEligibility.objects.all().delete()[0]
    counts["apt_snapshots"] = VotingVersionAptitudeSnapshot.objects.all().delete()[0]
    counts["version_snapshots"] = VotingVersionSnapshot.objects.all().delete()[0]
    counts["char_snapshots"] = VotingCharacterSnapshot.objects.all().delete()[0]
    counts["votings"] = Voting.objects.all().delete()[0]

    counts["import_jobs"] = ImportJob.objects.all().delete()[0]
    counts["sync_changes"] = SyncChange.objects.all().delete()[0]
    counts["sync_runs"] = SyncRun.objects.all().delete()[0]
    counts["images"] = ImageAsset.objects.all().delete()[0]
    counts["versions"] = CharacterVersion.objects.all().delete()[0]
    counts["characters"] = Character.objects.all().delete()[0]

# Reabilita as triggers fora da transação (não há eventos pendentes aqui).
with connection.cursor() as cursor:
    for table in TRIGGER_TABLES:
        cursor.execute(f"ALTER TABLE {table} ENABLE TRIGGER USER")

from django.contrib.auth import get_user_model  # noqa: E402

User = get_user_model()
print("removidos:", {key: value for key, value in counts.items() if key != "votings_cancelled"})
print(
    "restante:",
    {
        "usuarios": list(User.objects.values_list("username", "is_admin")),
        "fontes": list(CatalogSource.objects.values_list("name", "adapter", "enabled")),
        "personagens": Character.objects.count(),
        "versoes": CharacterVersion.objects.count(),
        "imagens": ImageAsset.objects.count(),
        "votacoes": Voting.objects.count(),
        "jobs": ImportJob.objects.count(),
        "runs": SyncRun.objects.count(),
    },
)
