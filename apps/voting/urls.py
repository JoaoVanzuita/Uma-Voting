"""Rotas de votações nos namespaces ``participant`` e ``admin``."""

from django.urls import path

from .views import admin as admin_views
from .views import participant as participant_views

app_name = "voting"

participant_patterns = [
    path("", participant_views.home, name="home"),
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
]

admin_patterns = [
    path("admin/", admin_views.dashboard, name="dashboard"),
]

urlpatterns = [*participant_patterns, *admin_patterns]
