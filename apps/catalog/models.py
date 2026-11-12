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
    adapter = models.SlugField(
        "conector",
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Chave do conector registrado; vazio desabilita a importação externa.",
    )
    options = models.JSONField(
        "opções do conector",
        default=dict,
        blank=True,
        help_text="Parâmetros não sensíveis do conector; nunca armazene credenciais.",
    )
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

    class Origin(models.TextChoices):
        MANUAL = "manual", "Manual"
        EXTERNAL = "external", "Importação externa"

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
    origin = models.CharField(
        "origem",
        max_length=20,
        choices=Origin.choices,
        default=Origin.MANUAL,
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


class ImportJob(models.Model):
    """Execução assíncrona de importação externa de catálogo e imagens."""

    class Kind(models.TextChoices):
        CATALOG = "catalog", "Catálogo"
        IMAGES = "images", "Imagens"
        FULL = "full", "Catálogo e imagens"

    class Status(models.TextChoices):
        QUEUED = "queued", "Na fila"
        RUNNING = "running", "Em execução"
        SUCCESS = "success", "Concluída"
        PARTIAL = "partial", "Concluída com falhas"
        FAILED = "failed", "Falhou"
        CANCELLED = "cancelled", "Cancelada"

    class Phase(models.TextChoices):
        QUEUED = "queued", "Aguardando"
        CATALOG = "catalog", "Catálogo"
        IMAGES = "images", "Imagens"
        FINISHED = "finished", "Encerrada"

    TERMINAL_STATUSES = frozenset(
        {
            Status.SUCCESS,
            Status.PARTIAL,
            Status.FAILED,
            Status.CANCELLED,
        }
    )

    source = models.ForeignKey(
        CatalogSource,
        on_delete=models.PROTECT,
        related_name="import_jobs",
        verbose_name="fonte",
    )
    kind = models.CharField("tipo", max_length=20, choices=Kind.choices)
    status = models.CharField(
        "situação",
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    phase = models.CharField(
        "fase",
        max_length=20,
        choices=Phase.choices,
        default=Phase.QUEUED,
    )
    options = models.JSONField("opções", default=dict, blank=True)
    progress_total = models.PositiveIntegerField("total do progresso", default=0)
    progress_done = models.PositiveIntegerField("progresso concluído", default=0)
    current_step = models.CharField("etapa atual", max_length=200, blank=True)
    report = models.JSONField("relatório", default=dict, blank=True)
    error_message = models.TextField("mensagem de erro", blank=True)
    cancel_requested = models.BooleanField("cancelamento solicitado", default=False)
    attempts = models.PositiveSmallIntegerField("tentativas", default=0)
    heartbeat_at = models.DateTimeField("último sinal", null=True, blank=True)
    started_at = models.DateTimeField("iniciada em", null=True, blank=True)
    finished_at = models.DateTimeField("finalizada em", null=True, blank=True)
    created_at = models.DateTimeField("criada em", auto_now_add=True)
    triggered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="catalog_import_jobs",
        verbose_name="disparada por",
        null=True,
        blank=True,
    )
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="cancelled_catalog_import_jobs",
        verbose_name="cancelada por",
        null=True,
        blank=True,
    )
    cancel_requested_at = models.DateTimeField("cancelamento solicitado em", null=True, blank=True)
    retry_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        related_name="retries",
        verbose_name="repetição de",
        null=True,
        blank=True,
    )
    sync_run = models.OneToOneField(
        SyncRun,
        on_delete=models.SET_NULL,
        related_name="import_job",
        verbose_name="execução de catálogo",
        null=True,
        blank=True,
    )

    class Meta:
        verbose_name = "execução de importação"
        verbose_name_plural = "execuções de importação"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status", "created_at"], name="catalog_import_status_idx"),
            models.Index(fields=["source", "-created_at"], name="catalog_import_source_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(kind__in=["catalog", "images", "full"]),
                name="import_job_kind_check",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        "queued",
                        "running",
                        "success",
                        "partial",
                        "failed",
                        "cancelled",
                    ]
                ),
                name="import_job_status_check",
            ),
            models.CheckConstraint(
                condition=models.Q(phase__in=["queued", "catalog", "images", "finished"]),
                name="import_job_phase_check",
            ),
            models.CheckConstraint(
                condition=models.Q(progress_done__lte=models.F("progress_total")),
                name="import_job_progress_check",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(
                            status__in=["success", "partial", "failed", "cancelled"],
                            finished_at__isnull=False,
                            phase="finished",
                        )
                    )
                    | (
                        ~models.Q(status__in=["success", "partial", "failed", "cancelled"])
                        & models.Q(finished_at__isnull=True)
                        & ~models.Q(phase="finished")
                    )
                ),
                name="import_job_terminal_check",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(status="cancelled")
                    | (
                        models.Q(cancelled_by__isnull=False)
                        & models.Q(cancel_requested_at__isnull=False)
                    )
                ),
                name="import_job_cancelled_check",
            ),
            models.UniqueConstraint(
                models.Value(1),
                condition=models.Q(status="running"),
                name="uniq_import_job_running",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.source.name} — {self.get_kind_display()} "
            f"({self.get_status_display()}, {self.created_at:%d/%m/%Y %H:%M})"
        )

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    @property
    def progress_percent(self) -> int:
        if not self.progress_total:
            return 0
        return min(100, round(self.progress_done * 100 / self.progress_total))
