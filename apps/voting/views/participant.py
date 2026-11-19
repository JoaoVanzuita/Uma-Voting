"""Views de participante: home, seleção, revisão, confirmação e cédula."""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from apps.catalog.models import Aptitude
from apps.core.permissions import require_eligible
from apps.voting.models import (
    Voting,
    VotingCharacterSnapshot,
    VotingStatus,
)
from apps.voting.services.ballots import (
    AlreadyVotedError,
    BallotError,
    InvalidBallotError,
    VotingNotOpenError,
    get_own_ballot,
    resolve_ballot_selection,
    submit_ballot,
)
from apps.voting.services.filters import FILTER_CATEGORIES, search_characters
from apps.voting.services.results import final_results, participation_summary

FILTER_LABELS = {
    "strategy": "Estratégia",
    "distance": "Distância",
    "surface": "Superfície",
}

FILTER_ORDER = {
    "strategy": ["front", "pace", "late", "end"],
    "distance": ["sprint", "mile", "medium", "long"],
    "surface": ["turf", "dirt"],
}

SELECTION_PREVIEW_LIMIT = 3


def _clean_ids(values) -> list[int]:
    cleaned: list[int] = []
    seen: set[int] = set()
    for value in values:
        try:
            pk = int(value)
        except TypeError, ValueError:
            continue
        if pk not in seen:
            seen.add(pk)
            cleaned.append(pk)
    return cleaned


def _request_values(request, key: str) -> list[str]:
    source = request.POST if request.method == "POST" else request.GET
    if key == "character_ids":
        # Os inputs ocultos guardam a ordem de clique. Eles vêm antes dos
        # checkboxes visíveis, que podem estar ausentes por causa de filtros.
        values = list(source.getlist("selected"))
        values += list(source.getlist("character_ids"))
        return values
    return list(source.getlist(key))


def _selected_ids(request) -> list[int]:
    return _clean_ids(_request_values(request, "character_ids"))


def _filters_from_request(request) -> dict[str, list[str]]:
    source = request.POST if request.method == "POST" else request.GET
    return {
        category: [value for value in source.getlist(category) if value]
        for category in FILTER_CATEGORIES
    }


def _filter_groups(selected_filters: dict[str, list[str]]) -> list[dict]:
    groups = []
    for category in FILTER_CATEGORIES:
        order = FILTER_ORDER[category]
        aptitudes = sorted(
            Aptitude.objects.filter(category=category),
            key=lambda aptitude: (
                order.index(aptitude.value) if aptitude.value in order else len(order)
            ),
        )
        groups.append(
            {
                "category": category,
                "label": FILTER_LABELS[category],
                "options": [
                    {
                        "value": aptitude.value,
                        "label": aptitude.label,
                        "checked": aptitude.value in selected_filters.get(category, []),
                    }
                    for aptitude in aptitudes
                ],
            }
        )
    return groups


def _selected_snapshots(voting: Voting, selected_ids: list[int]) -> list[VotingCharacterSnapshot]:
    """Snapshots selecionados na ordem em que foram escolhidos."""
    if not selected_ids:
        return []
    snapshots = VotingCharacterSnapshot.objects.filter(
        voting=voting,
        pk__in=selected_ids,
    ).select_related("image_asset")
    by_id = {snapshot.pk: snapshot for snapshot in snapshots}
    return [by_id[pk] for pk in selected_ids if pk in by_id]


def _selection_context(voting: Voting, selected_ids: list[int]) -> dict:
    """Contexto compartilhado pela página e pelo fragmento OOB."""
    snapshots = _selected_snapshots(voting, selected_ids)
    return {
        "selected_ids": selected_ids,
        "selected_snapshots": snapshots,
        "selected_preview": snapshots[:SELECTION_PREVIEW_LIMIT],
        "selected_more_count": max(0, len(snapshots) - SELECTION_PREVIEW_LIMIT),
        "selected_count": len(snapshots),
    }


def _get_voting(voting_id: int) -> Voting:
    voting = get_object_or_404(Voting, pk=voting_id)
    if voting.status == VotingStatus.CANCELLED:
        raise Http404("Votação não encontrada.")
    return voting


def _render_detail(
    request,
    voting: Voting,
    *,
    error: str | None = None,
    status: int = 200,
    selected_ids: list[int] | None = None,
):
    selected_filters = _filters_from_request(request)
    selected_ids = selected_ids if selected_ids is not None else _selected_ids(request)
    characters = search_characters(
        voting,
        selected_filters,
        request.POST.get("q", "") if request.method == "POST" else request.GET.get("q", ""),
        selected_ids,
    )
    context = {
        "voting": voting,
        "characters": characters,
        "filter_groups": _filter_groups(selected_filters),
        "query": request.POST.get("q", "")
        if request.method == "POST"
        else request.GET.get("q", ""),
        "error": error,
        "not_open": voting.status != VotingStatus.OPEN,
        "oob_summary": False,
        **_selection_context(voting, selected_ids),
    }
    return render(request, "participant/voting_detail.html", context, status=status)


def _closest_by_date(votings: list[Voting], field: str) -> Voting | None:
    """Escolhe a votação com a data mais próxima, com desempate estável."""
    if not votings:
        return None
    now = timezone.now()
    return min(
        votings,
        key=lambda voting: (
            getattr(voting, field) is None,
            getattr(voting, field) or now,
            voting.opens_at or now,
            voting.title,
        ),
    )


@login_required
def home(request):
    votings = list(
        Voting.objects.filter(
            status__in=[VotingStatus.OPEN, VotingStatus.SCHEDULED],
            eligibilities__user=request.user,
        )
        .distinct()
        .order_by("status", "opens_at", "title")
    )
    open_votings = [voting for voting in votings if voting.status == VotingStatus.OPEN]
    scheduled_votings = [voting for voting in votings if voting.status == VotingStatus.SCHEDULED]
    featured_voting = _closest_by_date(open_votings, "closes_at") or _closest_by_date(
        scheduled_votings, "opens_at"
    )
    other_votings = [
        voting for voting in votings if featured_voting is None or voting.pk != featured_voting.pk
    ]
    return render(
        request,
        "participant/home.html",
        {
            "votings": votings,
            "featured_voting": featured_voting,
            "other_votings": other_votings,
        },
    )


@login_required
def voting_detail(request, voting_id: int):
    voting = _get_voting(voting_id)
    require_eligible(request.user, voting)

    if voting.status == VotingStatus.CLOSED:
        if get_own_ballot(voting, request.user) is not None:
            return redirect("participant:ballot", voting_id=voting.pk)
        return redirect("participant:home")

    if voting.status == VotingStatus.DRAFT:
        raise Http404("Votação não encontrada.")

    if voting.status == VotingStatus.SCHEDULED:
        return render(
            request,
            "participant/voting_detail.html",
            {
                "voting": voting,
                "characters": [],
                "filter_groups": [],
                "not_open": True,
                "oob_summary": False,
                **_selection_context(voting, []),
            },
        )

    if get_own_ballot(voting, request.user) is not None:
        return redirect("participant:ballot", voting_id=voting.pk)

    return _render_detail(request, voting)


@login_required
def character_grid(request, voting_id: int):
    voting = _get_voting(voting_id)
    require_eligible(request.user, voting)

    if voting.status != VotingStatus.OPEN:
        return render(
            request,
            "participant/character_grid.html",
            {
                "voting": voting,
                "characters": [],
                "oob_summary": True,
                "not_open": True,
                **_selection_context(voting, []),
            },
            status=409,
        )

    selected_filters = _filters_from_request(request)
    selected_ids = _selected_ids(request)
    characters = search_characters(
        voting,
        selected_filters,
        request.GET.get("q", ""),
        selected_ids,
    )

    return render(
        request,
        "participant/character_grid.html",
        {
            "voting": voting,
            "characters": characters,
            "oob_summary": True,
            **_selection_context(voting, selected_ids),
        },
    )


@login_required
@require_POST
def review(request, voting_id: int):
    voting = _get_voting(voting_id)
    require_eligible(request.user, voting)

    if voting.status != VotingStatus.OPEN:
        return _render_detail(
            request,
            voting,
            error="Esta votação não está aberta.",
            status=409,
            selected_ids=_selected_ids(request),
        )

    if get_own_ballot(voting, request.user) is not None:
        return redirect("participant:ballot", voting_id=voting.pk)

    try:
        snapshots = resolve_ballot_selection(voting, _selected_ids(request))
    except BallotError as exc:
        return _render_detail(
            request,
            voting,
            error=exc.message,
            status=400,
            selected_ids=_selected_ids(request),
        )

    return render(
        request,
        "participant/review.html",
        {"voting": voting, "snapshots": snapshots},
    )


@login_required
@require_POST
def confirm(request, voting_id: int):
    voting = _get_voting(voting_id)
    require_eligible(request.user, voting)

    try:
        submit_ballot(voting, request.user, _selected_ids(request))
    except AlreadyVotedError as exc:
        ballot = get_own_ballot(voting, request.user)
        return render(
            request,
            "participant/ballot.html",
            {"voting": voting, "ballot": ballot, "error": exc.message},
            status=409,
        )
    except VotingNotOpenError as exc:
        return render(
            request,
            "participant/voting_unavailable.html",
            {"voting": voting, "message": exc.message},
            status=409,
        )
    except InvalidBallotError as exc:
        return _render_detail(
            request,
            voting,
            error=exc.message,
            status=400,
            selected_ids=_selected_ids(request),
        )

    messages.success(request, "Voto registrado com sucesso.")
    return redirect("participant:ballot", voting_id=voting.pk)


@login_required
def ballot(request, voting_id: int):
    voting = _get_voting(voting_id)
    require_eligible(request.user, voting)

    own_ballot = get_own_ballot(voting, request.user)
    if own_ballot is None:
        if voting.status == VotingStatus.OPEN:
            return redirect("participant:voting_detail", voting_id=voting.pk)
        return redirect("participant:home")

    return render(
        request,
        "participant/ballot.html",
        {"voting": voting, "ballot": own_ballot},
    )


@login_required
def result(request, voting_id: int):
    """Resultado final, disponível ao participante elegível somente após o encerramento."""
    voting = _get_voting(voting_id)
    require_eligible(request.user, voting)

    if voting.status != VotingStatus.CLOSED:
        raise Http404("O resultado estará disponível após o encerramento.")

    return render(
        request,
        "participant/result.html",
        {
            "voting": voting,
            "results": final_results(voting),
            "own_ballot": get_own_ballot(voting, request.user),
            "participation": participation_summary(voting),
        },
    )


@login_required
def history(request):
    """Histórico do participante, sem votações canceladas."""
    answered = (
        Voting.objects.filter(
            eligibilities__user=request.user,
            ballots__participant=request.user,
        )
        .exclude(status=VotingStatus.CANCELLED)
        .distinct()
        .order_by("-created_at")
    )
    closed_without_ballot = (
        Voting.objects.filter(
            eligibilities__user=request.user,
            status=VotingStatus.CLOSED,
        )
        .exclude(ballots__participant=request.user)
        .distinct()
        .order_by("-closed_at", "-created_at")
    )

    return render(
        request,
        "participant/history.html",
        {
            "answered": answered,
            "closed_without_ballot": closed_without_ballot,
        },
    )
