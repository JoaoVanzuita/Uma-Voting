"""Catálogo canônico de personagens, versões, aptidões e imagens."""

from __future__ import annotations

from django.conf import settings
from django.db import models


class CatalogSource(models.Model):
    """Origem dos dados e das imagens, com registro de termos e licença."""

    class Kind(models.TextChoices):
        HTML = "html", "HTML"
        API = "api", "API"
        FILE = "file", "Arquivo"
        MANUAL = "manual", "Manual"

    name = models.CharField("nome", max_length=100)
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices)
    base_url = models.URLField("URL base", blank=True)
    terms_url = models.URLField("URL dos termos", blank=True)
    license_note = models.TextField("nota de licença", blank=True)
    enabled = models.BooleanField("habilitada", default=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "fonte de catálogo"
        verbose_name_plural = "fontes de catálogo"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Character(models.Model):
    """Personagem canônica; versões nunca são opções independentes de votação."""

    stable_id = models.SlugField("identificador estável", max_length=120, unique=True)
    display_name = models.CharField("nome", max_length=150, db_index=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        verbose_name = "personagem"
        verbose_name_plural = "personagens"
        ordering = ["display_name"]

    def __str__(self) -> str:
        return self.display_name


class CharacterVersion(models.Model):
    """Versão/lançamento de uma personagem canônica."""

    character = models.ForeignKey(
        Character,
        on_delete=models.PROTECT,
        related_name="versions",
        verbose_name="personagem",
    )
    stable_id = models.SlugField("identificador estável", max_length=150, unique=True)
    display_name = models.CharField("nome da versão", max_length=200)
    release_date_global = models.DateField("lançamento global", null=True, blank=True)
    source = models.ForeignKey(
        CatalogSource,
        on_delete=models.PROTECT,
        related_name="versions",
        verbose_name="fonte",
        null=True,
        blank=True,
    )
    source_url = models.URLField("URL de origem", blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    updated_at = models.DateTimeField("atualizada em", auto_now=True)

    class Meta:
        verbose_name = "versão de personagem"
        verbose_name_plural = "versões de personagem"
        ordering = ["character", "display_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["character", "stable_id"],
                name="uniq_version_character_stable_id",
            ),
        ]
        indexes = [
            models.Index(
                fields=["character", "release_date_global"],
                name="catalog_ver_char_date_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.character.display_name} — {self.display_name}"


class Aptitude(models.Model):
    """Lookup de estratégia, distância e superfície."""

    class Category(models.TextChoices):
        STRATEGY = "strategy", "Estratégia"
        DISTANCE = "distance", "Distância"
        SURFACE = "surface", "Superfície"

    category = models.CharField("categoria", max_length=20, choices=Category.choices)
    value = models.CharField("valor", max_length=20)
    label = models.CharField("rótulo", max_length=50)

    class Meta:
        verbose_name = "aptidão"
        verbose_name_plural = "aptidões"
        ordering = ["category", "value"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "value"],
                name="uniq_aptitude_category_value",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.get_category_display()}: {self.label}"


class CharacterVersionAptitude(models.Model):
    """Associação N:N entre versão e aptidão."""

    version = models.ForeignKey(
        CharacterVersion,
        on_delete=models.CASCADE,
        related_name="version_aptitudes",
        verbose_name="versão",
    )
    aptitude = models.ForeignKey(
        Aptitude,
        on_delete=models.PROTECT,
        related_name="version_links",
        verbose_name="aptidão",
    )

    class Meta:
        verbose_name = "aptidão da versão"
        verbose_name_plural = "aptidões da versão"
        constraints = [
            models.UniqueConstraint(
                fields=["version", "aptitude"],
                name="uniq_version_aptitude",
            ),
        ]
        indexes = [
            models.Index(fields=["aptitude"], name="catalog_cva_aptitude_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.version} — {self.aptitude}"


class ImageAsset(models.Model):
    """Arquivo de imagem local e content-addressed associado a uma personagem."""

    class Status(models.TextChoices):
        VALID = "valid", "Válida"
        INVALID = "invalid", "Inválida"
        MISSING = "missing", "Ausente"

    character = models.ForeignKey(
        Character,
        on_delete=models.PROTECT,
        related_name="images",
        verbose_name="personagem",
    )
    file_path = models.CharField("caminho do arquivo", max_length=255, unique=True)
    is_current = models.BooleanField("corrente", default=False)
    status = models.CharField(
        "situação",
        max_length=20,
        choices=Status.choices,
        default=Status.MISSING,
    )
    checksum_sha256 = models.CharField(
        "checksum SHA-256",
        max_length=64,
        db_index=True,
        blank=True,
    )
    width = models.PositiveIntegerField("largura")
    height = models.PositiveIntegerField("altura")
    source = models.ForeignKey(
        CatalogSource,
        on_delete=models.PROTECT,
        related_name="images",
        verbose_name="fonte",
        null=True,
        blank=True,
    )
    source_url = models.URLField("URL de origem", blank=True)
    license_note = models.TextField("nota de licença", blank=True)
    validated_at = models.DateTimeField("validada em", null=True, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "imagem"
        verbose_name_plural = "imagens"
        ordering = ["character", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["character"],
                condition=models.Q(is_current=True),
                name="image_current_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["valid", "invalid", "missing"]),
                name="image_status_check",
            ),
            models.CheckConstraint(
                condition=models.Q(width__gt=0) & models.Q(height__gt=0),
                name="image_dimensions_check",
            ),
        ]

    def __str__(self) -> str:
        return self.file_path


class SyncRun(models.Model):
    """Execução de sincronização do catálogo; histórico imutável."""

    class Status(models.TextChoices):
        RUNNING = "running", "Em execução"
        SUCCESS = "success", "Sucesso"
        PARTIAL = "partial", "Parcial"
        FAILED = "failed", "Falhou"

    source = models.ForeignKey(
        CatalogSource,
        on_delete=models.PROTECT,
        related_name="sync_runs",
        verbose_name="fonte",
    )
    started_at = models.DateTimeField("iniciada em", auto_now_add=True)
    finished_at = models.DateTimeField("finalizada em", null=True, blank=True)
    status = models.CharField(
        "situação",
        max_length=20,
        choices=Status.choices,
        default=Status.RUNNING,
    )
    summary = models.TextField("resumo", blank=True)
    error_message = models.TextField("mensagem de erro", blank=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="catalog_sync_runs",
        verbose_name="disparada por",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "execução de sincronização"
        verbose_name_plural = "execuções de sincronização"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["status", "started_at"], name="catalog_sync_status_idx"),
        ]

    def __str__(self) -> str:
        return (
            f"{self.source.name} — {self.get_status_display()} ({self.started_at:%d/%m/%Y %H:%M})"
        )


class SyncChange(models.Model):
    """Mudança detectada por uma sincronização, pendente de revisão ou aplicada."""

    class ChangeType(models.TextChoices):
        NEW_CHARACTER = "new_character", "Nova personagem"
        UPDATE_CHARACTER = "update_character", "Atualização de personagem"
        NEW_VERSION = "new_version", "Nova versão"
        UPDATE_VERSION = "update_version", "Atualização de versão"
        APTITUDE_CHANGE = "aptitude_change", "Mudança de aptidões"

    class Status(models.TextChoices):
        AUTO_APPLIED = "auto_applied", "Aplicada automaticamente"
        PENDING = "pending", "Pendente"
        APPROVED = "approved", "Aprovada"
        REJECTED = "rejected", "Rejeitada"

    sync_run = models.ForeignKey(
        SyncRun,
        on_delete=models.PROTECT,
        related_name="changes",
        verbose_name="execução",
    )
    change_type = models.CharField("tipo", max_length=30, choices=ChangeType.choices)
    character = models.ForeignKey(
        Character,
        on_delete=models.PROTECT,
        related_name="sync_changes",
        verbose_name="personagem",
        null=True,
        blank=True,
    )
    version = models.ForeignKey(
        CharacterVersion,
        on_delete=models.PROTECT,
        related_name="sync_changes",
        verbose_name="versão",
        null=True,
        blank=True,
    )
    payload = models.JSONField("dados propostos", default=dict)
    status = models.CharField(
        "situação",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="catalog_sync_reviews",
        verbose_name="revisada por",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField("revisada em", null=True, blank=True)
    review_note = models.TextField("nota de revisão", blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)

    class Meta:
        verbose_name = "mudança de catálogo"
        verbose_name_plural = "mudanças de catálogo"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="catalog_change_status_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.get_change_type_display()} — {self.get_status_display()}"
