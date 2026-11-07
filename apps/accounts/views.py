"""Views de autenticação, logout e alternância de modo."""

from __future__ import annotations

import logging

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from apps.core.middleware import ADMIN_MODE_SESSION_KEY
from apps.core.permissions import is_admin_user

from .forms import AdminLoginForm, ParticipantLoginForm
from .services.auth import (
    AuthError,
    ThrottleError,
    login_admin,
    login_participant,
    logout_user,
)

logger = logging.getLogger("apps.accounts.views")


def _status_for(exc: AuthError) -> int:
    return 429 if isinstance(exc, ThrottleError) else 200


def participant_login(request):
    if request.user.is_authenticated:
        return redirect("participant:home")

    form = ParticipantLoginForm(request.POST or None)
    status = 200

    if request.method == "POST" and form.is_valid():
        try:
            login_participant(request, form.cleaned_data["username"])
        except AuthError as exc:
            form.add_error(None, exc.message)
            status = _status_for(exc)
        else:
            return redirect("participant:home")

    return render(request, "participant/login.html", {"form": form}, status=status)


def admin_login(request):
    if request.user.is_authenticated:
        if is_admin_user(request.user) and not getattr(request, "is_participant_mode", False):
            return redirect("admin:dashboard")
        return redirect("participant:home")

    form = AdminLoginForm(request.POST or None)
    status = 200

    if request.method == "POST" and form.is_valid():
        try:
            login_admin(
                request,
                form.cleaned_data["username"],
                form.cleaned_data["password"],
            )
        except AuthError as exc:
            form.add_error(None, exc.message)
            status = _status_for(exc)
        else:
            return redirect("admin:dashboard")

    return render(request, "admin/login.html", {"form": form}, status=status)


@login_required
@require_POST
def participant_logout(request):
    logout_user(request)
    return redirect("participant:login")


@login_required(login_url=reverse_lazy("admin:login"))
@require_POST
def admin_logout(request):
    if not is_admin_user(request.user):
        raise PermissionDenied("Acesso restrito a administradores.")
    logout_user(request)
    return redirect("admin:login")


@login_required(login_url=reverse_lazy("admin:login"))
@require_POST
def participant_mode(request):
    """Administrador alterna para a experiência de participante."""
    if not is_admin_user(request.user):
        raise PermissionDenied("Acesso restrito a administradores.")

    request.session[ADMIN_MODE_SESSION_KEY] = True
    logger.info("Modo participante ativado user_id=%s", request.user.pk)
    return redirect("participant:home")


@login_required(login_url=reverse_lazy("admin:login"))
@require_POST
def admin_mode(request):
    """Administrador retorna à experiência administrativa."""
    if not is_admin_user(request.user):
        raise PermissionDenied("Acesso restrito a administradores.")

    request.session[ADMIN_MODE_SESSION_KEY] = False
    logger.info("Modo administrativo ativado user_id=%s", request.user.pk)
    return redirect("admin:dashboard")
