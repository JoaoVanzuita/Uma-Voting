"""Rotas de votações nos namespaces ``participant`` e ``admin``."""

from django.urls import path

from .views import admin as admin_views
from .views import participant as participant_views

app_name = "voting"

participant_patterns = [
    path("", participant_views.home, name="home"),
    path("historico/", participant_views.history, name="history"),
    path(
        "votacoes/<int:voting_id>/",
        participant_views.voting_detail,
        name="voting_detail",
    ),
    path(
        "votacoes/<int:voting_id>/personagens/",
        participant_views.character_grid,
        name="character_grid",
    ),
    path(
        "votacoes/<int:voting_id>/revisar/",
        participant_views.review,
        name="review",
    ),
    path(
        "votacoes/<int:voting_id>/confirmar/",
        participant_views.confirm,
        name="confirm",
    ),
    path(
        "votacoes/<int:voting_id>/cedula/",
        participant_views.ballot,
        name="ballot",
    ),
    path(
        "votacoes/<int:voting_id>/resultado/",
        participant_views.result,
        name="result",
    ),
]

admin_patterns = [
    path("admin/", admin_views.dashboard, name="dashboard"),
    path("admin/votacoes/", admin_views.voting_list, name="voting_list"),
    path("admin/votacoes/nova/", admin_views.voting_create, name="voting_create"),
    path(
        "admin/votacoes/<int:voting_id>/",
        admin_views.voting_detail,
        name="voting_detail",
    ),
    path(
        "admin/votacoes/<int:voting_id>/editar/",
        admin_views.voting_edit,
        name="voting_edit",
    ),
    path(
        "admin/votacoes/<int:voting_id>/elegiveis/",
        admin_views.voting_eligible,
        name="voting_eligible",
    ),
    path(
        "admin/votacoes/<int:voting_id>/agendar/",
        admin_views.voting_schedule,
        name="voting_schedule",
    ),
    path(
        "admin/votacoes/<int:voting_id>/abrir/",
        admin_views.voting_open,
        name="voting_open",
    ),
    path(
        "admin/votacoes/<int:voting_id>/encerrar/",
        admin_views.voting_close,
        name="voting_close",
    ),
    path(
        "admin/votacoes/<int:voting_id>/cancelar/",
        admin_views.voting_cancel,
        name="voting_cancel",
    ),
    path(
        "admin/votacoes/<int:voting_id>/resultados/",
        admin_views.voting_results,
        name="voting_results",
    ),
    path(
        "admin/votacoes/<int:voting_id>/participacao/",
        admin_views.voting_participation,
        name="voting_participation",
    ),
    path(
        "admin/votacoes/<int:voting_id>/cedulas/<int:user_id>/excluir/",
        admin_views.ballot_delete,
        name="ballot_delete",
    ),
]

urlpatterns = [*participant_patterns, *admin_patterns]
