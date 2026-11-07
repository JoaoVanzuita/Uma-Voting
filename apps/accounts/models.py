"""Modelo de usuário único: administradores e participantes compartilham a identidade."""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser):
    """Usuário do sistema.

    Administradores autenticam com senha; participantes usam username-only e
    recebem ``set_unusable_password()``. Não há e-mail, nome legal nem perfil.
    """

    # ``unique=True`` satisfaz a checagem auth.E003 do Django; o índice
    # funcional abaixo garante a unicidade case-insensitive exigida.
    username = models.CharField("username", max_length=150, unique=True)
    is_admin = models.BooleanField("administrador", default=False)
    is_active = models.BooleanField("ativo", default=True)
    date_joined = models.DateTimeField("data de cadastro", default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "usuário"
        verbose_name_plural = "usuários"
        ordering = ["username"]
        constraints = [
            models.UniqueConstraint(
                Lower("username"),
                name="uniq_user_username_ci",
            ),
        ]

    def __str__(self) -> str:
        return self.username

    @property
    def display_name(self) -> str:
        """A interface exibe somente o username, preservando a grafia cadastrada."""
        return self.username
