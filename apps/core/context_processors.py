"""Context processors compartilhados."""

from __future__ import annotations


def admin_mode(request) -> dict[str, bool]:
    """Disponibiliza o modo participante do administrador aos templates."""
    return {"is_participant_mode": getattr(request, "is_participant_mode", False)}
