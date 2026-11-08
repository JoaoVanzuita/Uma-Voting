"""Rotas do app de catálogo no namespace ``admin``."""

from django.urls import path

from . import views

app_name = "catalog"

admin_patterns = [
    path("admin/catalogo/", views.catalog_status, name="catalog_status"),
    path("admin/catalogo/sincronizar/", views.catalog_sync, name="catalog_sync"),
    path(
        "admin/catalogo/sincronizacoes/<int:sync_id>/",
        views.catalog_sync_detail,
        name="catalog_sync_detail",
    ),
    path(
        "admin/catalogo/mudancas/<int:change_id>/aprovar/",
        views.catalog_approve,
        name="catalog_approve",
    ),
    path(
        "admin/catalogo/mudancas/<int:change_id>/rejeitar/",
        views.catalog_reject,
        name="catalog_reject",
    ),
    path(
        "admin/catalogo/personagens/",
        views.catalog_characters,
        name="catalog_characters",
    ),
    path("admin/catalogo/imagens/", views.catalog_images, name="catalog_images"),
    path(
        "admin/catalogo/imagens/validar/",
        views.catalog_images_validate,
        name="catalog_images_validate",
    ),
]

urlpatterns = [*admin_patterns]
