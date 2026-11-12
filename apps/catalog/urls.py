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
    path("admin/catalogo/importar/", views.catalog_import, name="catalog_import"),
    path(
        "admin/catalogo/importacoes/",
        views.catalog_import_list,
        name="catalog_import_list",
    ),
    path(
        "admin/catalogo/importacoes/<int:job_id>/",
        views.catalog_import_detail,
        name="catalog_import_detail",
    ),
    path(
        "admin/catalogo/importacoes/<int:job_id>/status/",
        views.catalog_import_status,
        name="catalog_import_status",
    ),
    path(
        "admin/catalogo/importacoes/<int:job_id>/cancelar/",
        views.catalog_import_cancel,
        name="catalog_import_cancel",
    ),
    path(
        "admin/catalogo/importacoes/<int:job_id>/repetir/",
        views.catalog_import_retry,
        name="catalog_import_retry",
    ),
    path(
        "admin/catalogo/fontes/<int:source_id>/verificar/",
        views.catalog_source_check,
        name="catalog_source_check",
    ),
]

urlpatterns = [*admin_patterns]
