"""Autorização server-side compartilhada por views e serviços."""

from __future__ import annotations

from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied


def is_active_user(user) -> bool:
    return bool(getattr(user, "is_authenticated", False) and getattr(user, "is_active", False))


def is_admin_user(user) -> bool:
    return is_active_user(user) and bool(getattr(user, "is_admin", False))


class ActiveUserRequiredMixin(LoginRequiredMixin):
    """Exige sessão ativa e conta não desativada."""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not request.user.is_active:
            raise PermissionDenied("Conta desativada.")
        return super().dispatch(request, *args, **kwargs)


class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """Restringe a área administrativa a administradores ativos.

    Visitantes não autenticados são redirecionados ao login; usuários
    autenticados sem privilégio recebem 403.
    """

    def test_func(self) -> bool:
        return is_admin_user(self.request.user)

    def handle_no_permission(self):
        if self.request.user.is_authenticated:
            raise PermissionDenied("Acesso restrito a administradores.")
        return super().handle_no_permission()


def is_eligible(user, voting) -> bool:
    """Verifica, no servidor, se o usuário está elegível na votação."""
    if not is_active_user(user):
        return False

    # Import tardio: o app de votações é criado na Fase 4 e core não deve
    # depender dele no carregamento do módulo.
    from apps.voting.models import VotingEligibility

    return VotingEligibility.objects.filter(voting=voting, user=user).exists()


def require_eligible(user, voting) -> None:
    if not is_eligible(user, voting):
        raise PermissionDenied("Você não é elegível para esta votação.")
