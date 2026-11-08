"""Votações, elegibilidade, snapshots imutáveis e cédulas."""

from __future__ import annotations

from datetime import date

from django.conf import settings
from django.db import models
from django.db.models import F, Q


class Mode(models.TextChoices):
    MANUAL = "manual", "Manual"
    AUTOMATIC = "automatic", "Automática"


class VotingStatus(models.TextChoices):
    DRAFT = "draft", "Rascunho"
    SCHEDULED = "scheduled", "Agendada"
    OPEN = "open", "Aberta"
    CLOSED = "closed", "Encerrada"
    CANCELLED = "cancelled", "Cancelada"


DEFAULT_CATALOG_CUTOFF = date(2026, 12, 1)


class Voting(models.Model):
    title = models.CharField("título", max_length=200)
    description = models.TextField("descrição", blank=True)
    choices_count = models.PositiveSmallIntegerField("quantidade de escolhas", default=3)
    catalog_cutoff_date = models.DateField(
        "data de corte do catálogo",
        default=DEFAULT_CATALOG_CUTOFF,
    )
    opens_at = models.DateTimeField("abertura", null=True, blank=True)
    closes_at = models.DateTimeField("encerramento", null=True, blank=True)
    open_mode = models.CharField(
        "modo de abertura",
        max_length=10,
        choices=Mode.choices,
        default=Mode.MANUAL,
    )
    close_mode = models.CharField(
        "modo de encerramento",
        max_length=10,
        choices=Mode.choices,
        default=Mode.MANUAL,
    )
    status = models.CharField(
        "estado",
        max_length=12,
        choices=VotingStatus.choices,
        default=VotingStatus.DRAFT,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_votings",
        verbose_name="criada por",
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)
    eligible_frozen_at = models.DateTimeField("elegíveis congelados em", null=True, blank=True)
    catalog_frozen_at = models.DateTimeField("catálogo congelado em", null=True, blank=True)
    opened_at = models.DateTimeField("aberta em", null=True, blank=True)
    closed_at = models.DateTimeField("encerrada em", null=True, blank=True)
    cancelled_at = models.DateTimeField("cancelada em", null=True, blank=True)

    class Meta:
        verbose_name = "votação"
        verbose_name_plural = "votações"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(choices_count__gt=0),
                name="voting_choices_count_positive",
            ),
            models.CheckConstraint(
                condition=Q(opens_at__isnull=True)
                | Q(closes_at__isnull=True)
                | Q(closes_at__gt=F("opens_at")),
                name="voting_dates_order",
            ),
            models.CheckConstraint(
                condition=~Q(open_mode=Mode.AUTOMATIC) | Q(opens_at__isnull=False),
                name="voting_open_mode_dates",
            ),
            models.CheckConstraint(
                condition=~Q(close_mode=Mode.AUTOMATIC) | Q(closes_at__isnull=False),
                name="voting_close_mode_dates",
            ),
            models.CheckConstraint(
                condition=Q(status__in=VotingStatus.values),
                name="voting_status_check",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "opens_at"], name="voting_status_opens_idx"),
            models.Index(fields=["status", "closes_at"], name="voting_status_closes_idx"),
        ]

    def __str__(self) -> str:
        return self.title


class VotingEligibility(models.Model):
    voting = models.ForeignKey(
        Voting,
        on_delete=models.PROTECT,
        related_name="eligibilities",
        verbose_name="votação",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="voting_eligibilities",
        verbose_name="usuário",
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "elegibilidade"
        verbose_name_plural = "elegibilidades"
        constraints = [
            models.UniqueConstraint(
                fields=["voting", "user"],
                name="uniq_voting_eligibility",
            ),
        ]
        indexes = [
            models.Index(fields=["user"], name="voting_eligibility_user_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.voting} — {self.user}"


class VotingCharacterSnapshot(models.Model):
    voting = models.ForeignKey(
        Voting,
        on_delete=models.PROTECT,
        related_name="character_snapshots",
        verbose_name="votação",
    )
    source_character = models.ForeignKey(
        "catalog.Character",
        on_delete=models.PROTECT,
        related_name="snapshots",
        verbose_name="personagem de origem",
    )
    stable_id = models.SlugField("identificador estável", max_length=120)
    display_name = models.CharField("nome", max_length=150)
    image_asset = models.ForeignKey(
        "catalog.ImageAsset",
        on_delete=models.PROTECT,
        related_name="snapshots",
        verbose_name="imagem",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "snapshot de personagem"
        verbose_name_plural = "snapshots de personagem"
        ordering = ["display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["voting", "source_character"],
                name="uniq_voting_source_character",
            ),
            models.UniqueConstraint(
                fields=["voting", "stable_id"],
                name="uniq_voting_snapshot_stable_id",
            ),
        ]
        indexes = [
            models.Index(fields=["voting", "display_name"], name="voting_snapshot_name_idx"),
        ]

    def __str__(self) -> str:
        return self.display_name


class VotingVersionSnapshot(models.Model):
    character_snapshot = models.ForeignKey(
        VotingCharacterSnapshot,
        on_delete=models.CASCADE,
        related_name="version_snapshots",
        verbose_name="snapshot de personagem",
    )
    source_version = models.ForeignKey(
        "catalog.CharacterVersion",
        on_delete=models.PROTECT,
        related_name="snapshots",
        verbose_name="versão de origem",
    )
    stable_id = models.SlugField("identificador estável", max_length=150)
    release_date_global = models.DateField("lançamento global")
    created_at = models.DateTimeField("criado em", auto_now_add=True)

    class Meta:
        verbose_name = "snapshot de versão"
        verbose_name_plural = "snapshots de versão"
        constraints = [
            models.UniqueConstraint(
                fields=["character_snapshot", "source_version"],
                name="uniq_snapshot_source_version",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character_snapshot} — {self.stable_id}"


class VotingVersionAptitudeSnapshot(models.Model):
    version_snapshot = models.ForeignKey(
        VotingVersionSnapshot,
        on_delete=models.CASCADE,
        related_name="aptitude_snapshots",
        verbose_name="snapshot de versão",
    )
    aptitude = models.ForeignKey(
        "catalog.Aptitude",
        on_delete=models.PROTECT,
        related_name="snapshot_links",
        verbose_name="aptidão",
    )

    class Meta:
        verbose_name = "aptidão do snapshot"
        verbose_name_plural = "aptidões do snapshot"
        constraints = [
            models.UniqueConstraint(
                fields=["version_snapshot", "aptitude"],
                name="uniq_snapshot_aptitude",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.version_snapshot} — {self.aptitude}"


class Ballot(models.Model):
    voting = models.ForeignKey(
        Voting,
        on_delete=models.PROTECT,
        related_name="ballots",
        verbose_name="votação",
    )
    participant = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="ballots",
        verbose_name="participante",
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "cédula"
        verbose_name_plural = "cédulas"
        constraints = [
            models.UniqueConstraint(
                fields=["voting", "participant"],
                name="uniq_ballot_voting_participant",
            ),
        ]
        indexes = [
            models.Index(fields=["participant"], name="ballot_participant_idx"),
            models.Index(fields=["voting", "created_at"], name="ballot_voting_created_idx"),
        ]

    def __str__(self) -> str:
        return f"Cédula de {self.participant} em {self.voting}"


class BallotChoice(models.Model):
    ballot = models.ForeignKey(
        Ballot,
        on_delete=models.CASCADE,
        related_name="choices",
        verbose_name="cédula",
    )
    character_snapshot = models.ForeignKey(
        VotingCharacterSnapshot,
        on_delete=models.PROTECT,
        related_name="ballot_choices",
        verbose_name="personagem",
    )

    class Meta:
        verbose_name = "escolha da cédula"
        verbose_name_plural = "escolhas da cédula"
        constraints = [
            models.UniqueConstraint(
                fields=["ballot", "character_snapshot"],
                name="uniq_ballot_character_snapshot",
            ),
        ]
        indexes = [
            models.Index(
                fields=["character_snapshot"],
                name="ballot_choice_snapshot_idx",
            ),
            models.Index(
                fields=["character_snapshot", "ballot"],
                name="ballot_choice_snap_ballot_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.ballot} — {self.character_snapshot}"
