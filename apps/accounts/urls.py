"""Rotas de contas nos namespaces ``participant`` e ``admin``."""

from django.urls import path

from . import views

app_name = "accounts"

participant_patterns = [
    path("entrar/", views.participant_login, name="login"),
    path("sair/", views.participant_logout, name="logout"),
    path("participante/modo-admin/", views.admin_mode, name="admin_mode"),
]

admin_patterns = [
    path("admin/entrar/", views.admin_login, name="login"),
    path("admin/sair/", views.admin_logout, name="logout"),
    path("admin/modo-participante/", views.participant_mode, name="participant_mode"),
]

urlpatterns = [*participant_patterns, *admin_patterns]
