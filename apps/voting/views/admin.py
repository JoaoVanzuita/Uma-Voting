"""Painel administrativo (esqueleto até a Fase 10)."""

from __future__ import annotations

from django.views.generic import TemplateView

from apps.core.permissions import AdminRequiredMixin


class AdminDashboardView(AdminRequiredMixin, TemplateView):
    template_name = "admin/dashboard.html"


dashboard = AdminDashboardView.as_view()
