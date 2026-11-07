"""Views de autenticação, logout e alternância de modo."""

from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST

from apps.core.middleware import ADMIN_MODE_SESSION_KEY
from apps.core.permissions import admin_required, is_admin_user

from .forms import AdminLoginForm, ParticipantForm, ParticipantImportForm, ParticipantLoginForm
from .models import User
from .services.auth import (
    AuthError,
    ThrottleError,
    login_admin,
    login_participant,
    logout_user,
)
from .services.imports import import_participants, import_rows
from .services.participants import (
    ParticipantError,
    create_participant,
    deactivate_participant,
    update_participant,
)

logger = logging.getLogger("apps.accounts.views")

PARTICIPANT_IMPORT_SESSION_KEY = "participant_import_preview"


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


# ---------------------------------------------------------------------------
# Participantes (área administrativa)
# ---------------------------------------------------------------------------


@admin_required
def participant_list(request):
    query = request.GET.get("q", "").strip()
    participants = User.objects.all()
    if query:
        participants = participants.filter(username__icontains=query)
    participants = participants.order_by("username")

    return render(
        request,
        "admin/participants/list.html",
        {"participants": participants, "query": query},
    )


@admin_required
def participant_create(request):
    form = ParticipantForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            participant = create_participant(form.cleaned_data["username"])
        except ParticipantError as exc:
            form.add_error("username", exc.message)
        else:
            messages.success(
                request,
                f"Participante '{participant.username}' cadastrado com sucesso.",
            )
            return redirect("admin:participant_list")

    return render(
        request,
        "admin/participants/form.html",
        {"form": form, "instance": None},
    )


@admin_required
def participant_edit(request, user_id: int):
    participant = get_object_or_404(User, pk=user_id)
    if participant.is_admin:
        raise PermissionDenied(
            "Contas administrativas são somente leitura na área de participantes."
        )

    form = ParticipantForm(request.POST or None, instance=participant)

    if request.method == "POST" and form.is_valid():
        try:
            participant = update_participant(
                participant,
                form.cleaned_data["username"],
            )
        except ParticipantError as exc:
            form.add_error("username", exc.message)
        else:
            messages.success(
                request,
                f"Participante '{participant.username}' atualizado com sucesso.",
            )
            return redirect("admin:participant_list")

    return render(
        request,
        "admin/participants/form.html",
        {"form": form, "instance": participant},
    )


@admin_required
@require_POST
def participant_deactivate(request, user_id: int):
    participant = get_object_or_404(User, pk=user_id)
    if participant.is_admin:
        raise PermissionDenied(
            "Contas administrativas são somente leitura na área de participantes."
        )

    deactivate_participant(participant)
    messages.success(
        request,
        f"Participante '{participant.username}' desativado.",
    )
    return redirect("admin:participant_list")


@admin_required
def participant_import(request):
    form = ParticipantImportForm()
    report = None

    if request.method == "POST":
        action = request.POST.get("action", "preview")

        if action == "apply":
            preview = request.session.pop(PARTICIPANT_IMPORT_SESSION_KEY, None)
            if not preview:
                messages.error(
                    request,
                    "Nenhuma importação pendente. Envie o arquivo novamente.",
                )
                return redirect("admin:participant_import")

            report = import_rows(
                preview["rows"],
                apply=True,
                total_lines=preview.get("total_lines"),
            )
            if report.has_errors:
                messages.error(request, "Nenhum participante foi importado.")
            else:
                messages.success(
                    request,
                    f"{report.imported_count} participante(s) importado(s) com sucesso.",
                )
        else:
            form = ParticipantImportForm(request.POST, request.FILES)
            if form.is_valid():
                report = import_participants(
                    form.cleaned_data["file"],
                    apply=False,
                )
                if report.has_errors:
                    request.session.pop(PARTICIPANT_IMPORT_SESSION_KEY, None)
                else:
                    request.session[PARTICIPANT_IMPORT_SESSION_KEY] = {
                        "rows": report.valid_rows,
                        "total_lines": report.total_lines,
                    }

    return render(
        request,
        "admin/participants/import.html",
        {"form": form, "report": report},
    )
