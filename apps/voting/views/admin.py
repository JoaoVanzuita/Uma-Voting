"""Views administrativas de configuração de votações (Fase 7)."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.catalog.models import Character, ImageAsset, SyncChange
from apps.core.exceptions import PreconditionError
from apps.core.permissions import admin_required
from apps.voting.forms import EligibleAddForm, VotingForm
from apps.voting.models import (
    Ballot,
    Voting,
    VotingEligibility,
    VotingStatus,
)
from apps.voting.services.ballots import delete_ballot_admin
from apps.voting.services.eligibility import (
    EligibilityError,
    add_eligible,
    remove_eligible,
)
from apps.voting.services.lifecycle import (
    VotingConfigError,
    VotingStateError,
    cancel_voting,
    close_voting,
    create_voting,
    evaluate_open_preconditions,
    open_voting,
    schedule_voting,
    update_voting,
)
from apps.voting.services.results import (
    aggregate_results,
    final_results,
    participation,
)


@admin_required
def dashboard(request):
    active_participants = User.objects.filter(is_active=True).count()
    open_votings = Voting.objects.filter(status=VotingStatus.OPEN).count()
    scheduled_rows = list(
        Voting.objects.filter(status=VotingStatus.SCHEDULED).order_by("opens_at", "title")
    )
    scheduled_votings = len(scheduled_rows)
    pending_changes = SyncChange.objects.filter(status=SyncChange.Status.PENDING).count()
    characters_without_image = (
        Character.objects.exclude(
            images__is_current=True,
            images__status=ImageAsset.Status.VALID,
        )
        .distinct()
        .count()
    )
    invalid_images = ImageAsset.objects.filter(
        is_current=True,
        status=ImageAsset.Status.INVALID,
    ).count()

    scheduled_blocked = []
    for voting in scheduled_rows:
        problems = evaluate_open_preconditions(voting).problems()
        if problems:
            scheduled_blocked.append({"voting": voting, "problems": problems})
    action_count = pending_changes + invalid_images + len(scheduled_blocked)

    latest_votings = Voting.objects.select_related("created_by").order_by("-created_at")[:5]
    ongoing_votings = Voting.objects.filter(
        status__in=[VotingStatus.OPEN, VotingStatus.SCHEDULED]
    ).order_by("status", "opens_at", "title")[:5]

    return render(
        request,
        "admin/dashboard.html",
        {
            "active_participants": active_participants,
            "open_votings": open_votings,
            "scheduled_votings": scheduled_votings,
            "pending_changes": pending_changes,
            "characters_without_image": characters_without_image,
            "invalid_images": invalid_images,
            "scheduled_blocked": scheduled_blocked,
            "action_count": action_count,
            "latest_votings": latest_votings,
            "ongoing_votings": ongoing_votings,
        },
    )


@admin_required
def voting_list(request):
    status = request.GET.get("status", "")
    query = request.GET.get("q", "").strip()

    votings = Voting.objects.select_related("created_by")
    if status in VotingStatus.values:
        votings = votings.filter(status=status)
    if query:
        votings = votings.filter(title__icontains=query)

    return render(
        request,
        "admin/voting/list.html",
        {
            "votings": votings.order_by("-created_at"),
            "status": status,
            "query": query,
            "status_choices": VotingStatus.choices,
        },
    )


@admin_required
def voting_create(request):
    form = VotingForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            voting = create_voting(form.cleaned_data, request.user)
        except VotingConfigError as exc:
            form.add_error(None, exc.message)
        else:
            messages.success(request, f"Votação '{voting.title}' criada em rascunho.")
            return redirect("admin:voting_detail", voting_id=voting.pk)

    return render(
        request,
        "admin/voting/form.html",
        {"form": form, "voting": None},
    )


@admin_required
def voting_edit(request, voting_id: int):
    voting = get_object_or_404(Voting, pk=voting_id)

    if voting.status != VotingStatus.DRAFT:
        messages.error(
            request,
            "A configuração só pode ser editada enquanto a votação está em rascunho.",
        )
        return redirect("admin:voting_detail", voting_id=voting.pk)

    form = VotingForm(request.POST or None, instance=voting)

    if request.method == "POST" and form.is_valid():
        try:
            voting = update_voting(voting, form.cleaned_data)
        except (VotingConfigError, VotingStateError) as exc:
            form.add_error(None, exc.message)
        else:
            messages.success(request, "Configuração da votação atualizada.")
            return redirect("admin:voting_detail", voting_id=voting.pk)

    return render(
        request,
        "admin/voting/form.html",
        {"form": form, "voting": voting},
    )


@admin_required
def voting_detail(request, voting_id: int):
    voting = get_object_or_404(
        Voting.objects.select_related("created_by"),
        pk=voting_id,
    )
    preconditions = evaluate_open_preconditions(voting)
    eligible_count = VotingEligibility.objects.filter(voting=voting).count()
    ballots = (
        Ballot.objects.filter(voting=voting)
        .select_related("participant")
        .order_by("participant__username")
    )
    ballot_count = ballots.count()

    return render(
        request,
        "admin/voting/detail.html",
        {
            "voting": voting,
            "preconditions": preconditions,
            "eligible_count": eligible_count,
            "ballot_count": ballot_count,
            "ballots": ballots,
            "can_edit": voting.status == VotingStatus.DRAFT,
            "can_open": (
                voting.status == VotingStatus.DRAFT
                and voting.open_mode == "manual"
                and preconditions.ok
            ),
            "can_close": voting.status == VotingStatus.OPEN,
            "can_cancel": voting.status != VotingStatus.CANCELLED,
        },
    )


@admin_required
def voting_eligible(request, voting_id: int):
    voting = get_object_or_404(Voting, pk=voting_id)

    if voting.status != VotingStatus.DRAFT:
        messages.error(
            request,
            "Elegíveis só podem ser alterados enquanto a votação está em rascunho.",
        )
        return redirect("admin:voting_detail", voting_id=voting.pk)

    add_form = EligibleAddForm(voting=voting)

    if request.method == "POST":
        action = request.POST.get("action", "add")
        try:
            if action == "remove":
                user_id = request.POST.get("user_id")
                removed = remove_eligible(voting, [user_id])
                messages.success(request, f"{removed} elegível(is) removido(s).")
            else:
                add_form = EligibleAddForm(request.POST, voting=voting)
                if add_form.is_valid():
                    added = add_eligible(voting, add_form.cleaned_data["users"])
                    messages.success(request, f"{added} elegível(is) adicionado(s).")
        except EligibilityError as exc:
            messages.error(request, exc.message)
        return redirect("admin:voting_eligible", voting_id=voting.pk)

    eligibilities = (
        VotingEligibility.objects.filter(voting=voting)
        .select_related("user")
        .order_by("user__username")
    )
    return render(
        request,
        "admin/voting/eligible.html",
        {
            "voting": voting,
            "eligibilities": eligibilities,
            "add_form": add_form,
        },
    )


@admin_required
@require_POST
def voting_schedule(request, voting_id: int):
    voting = get_object_or_404(Voting, pk=voting_id)
    try:
        schedule_voting(voting)
    except (VotingConfigError, VotingStateError, PreconditionError) as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, "Votação agendada. A configuração ficou bloqueada.")
    return redirect("admin:voting_detail", voting_id=voting.pk)


@admin_required
@require_POST
def voting_open(request, voting_id: int):
    voting = get_object_or_404(Voting, pk=voting_id)
    try:
        open_voting(voting, "admin")
    except (VotingStateError, VotingConfigError, PreconditionError) as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, "Votação aberta e catálogo congelado.")
    return redirect("admin:voting_detail", voting_id=voting.pk)


@admin_required
@require_POST
def voting_close(request, voting_id: int):
    voting = get_object_or_404(Voting, pk=voting_id)
    try:
        close_voting(voting, "admin")
    except VotingStateError as exc:
        messages.error(request, exc.message)
    else:
        messages.success(request, "Votação encerrada.")
    return redirect("admin:voting_detail", voting_id=voting.pk)


@admin_required
@require_POST
def voting_cancel(request, voting_id: int):
    voting = get_object_or_404(Voting, pk=voting_id)
    reason = request.POST.get("reason", "").strip()
    cancel_voting(voting, admin=request.user, reason=reason or None)
    messages.success(request, "Votação cancelada e cédulas eliminadas.")
    return redirect("admin:voting_detail", voting_id=voting.pk)


@admin_required
@require_POST
def ballot_delete(request, voting_id: int, user_id: int):
    voting = get_object_or_404(Voting, pk=voting_id)
    participant = get_object_or_404(get_user_model(), pk=user_id)

    try:
        deleted = delete_ballot_admin(voting, participant, request.user)
    except (VotingStateError, PreconditionError) as exc:
        messages.error(request, exc.message)
    else:
        if deleted:
            messages.success(request, "Cédula excluída. O participante pode votar novamente.")
        else:
            messages.info(request, "Não havia cédula para este participante.")
    return redirect("admin:voting_detail", voting_id=voting.pk)


@admin_required
def voting_results(request, voting_id: int):
    voting = get_object_or_404(Voting, pk=voting_id)
    rows = aggregate_results(voting)
    ranked = final_results(voting) if voting.status == VotingStatus.CLOSED else []

    return render(
        request,
        "admin/voting/results.html",
        {
            "voting": voting,
            "results": rows,
            "ranked": ranked,
            "official": voting.status == VotingStatus.CLOSED,
        },
    )


@admin_required
def voting_participation(request, voting_id: int):
    voting = get_object_or_404(Voting, pk=voting_id)
    rows = participation(voting)
    voted_count = sum(1 for row in rows if row.voted)

    return render(
        request,
        "admin/voting/participation.html",
        {
            "voting": voting,
            "rows": rows,
            "voted_count": voted_count,
            "eligible_count": len(rows),
        },
    )
