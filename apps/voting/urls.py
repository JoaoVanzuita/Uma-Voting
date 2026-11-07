"""Rotas de votações nos namespaces ``participant`` e ``admin``."""

from django.urls import path

from .views import admin as admin_views
from .views import participant as participant_views

app_name = "voting"

participant_patterns = [
    path("", participant_views.home, name="home"),
]

admin_patterns = [
    path("admin/", admin_views.dashboard, name="dashboard"),
]

urlpatterns = [*participant_patterns, *admin_patterns]
