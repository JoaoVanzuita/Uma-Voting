"""Manager do modelo de usuário único do sistema."""

from __future__ import annotations

from django.contrib.auth.base_user import BaseUserManager


class UserManager(BaseUserManager):
    """Cria usuários e resolve o login por username sem diferenciar maiúsculas."""

    use_in_migrations = True

    def _create_user(self, username: str, password: str | None, **extra_fields):
        if not username or not username.strip():
            raise ValueError("O username é obrigatório.")

        user = self.model(username=username.strip(), **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, username: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_admin", False)
        extra_fields.setdefault("is_active", True)
        return self._create_user(username, password, **extra_fields)

    def create_superuser(self, username: str, password: str | None = None, **extra_fields):
        extra_fields.setdefault("is_admin", True)
        extra_fields.setdefault("is_active", True)
        if not password:
            raise ValueError("Administradores exigem senha.")
        return self._create_user(username, password, **extra_fields)

    def get_by_natural_key(self, username: str):
        """Busca case-insensitive, como exigido pelo login administrativo."""
        return self.get(username__iexact=username)
