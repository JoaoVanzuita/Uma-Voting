#!/usr/bin/env python
"""Utilitário de linha de comando do Django."""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover - ambiente sem dependências
        raise ImportError(
            "Não foi possível importar o Django. Verifique se o ambiente virtual está "
            "ativado e se as dependências foram instaladas com `uv sync`."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
