"""Home do participante (esqueleto até a Fase 4)."""

from __future__ import annotations

from django.views.generic import TemplateView

from apps.core.permissions import ActiveUserRequiredMixin


class ParticipantHomeView(ActiveUserRequiredMixin, TemplateView):
    template_name = "participant/home.html"


home = ParticipantHomeView.as_view()
