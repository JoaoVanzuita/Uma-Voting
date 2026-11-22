"""Fixture de storage de mídia em diretório temporário para os testes."""

from __future__ import annotations

import pytest
from django.core.files.storage import storages

from apps.catalog.services import media


@pytest.fixture
def media_storage(settings, tmp_path):
    """Aponta o storage de mídia para ``tmp_path`` durante o teste.

    ``STORAGES`` é resolvido por processo; além de trocar a setting, o cache do
    ``StorageHandler`` é limpo (antes e depois) para usar o novo diretório.
    """
    settings.STORAGES = {
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
            "OPTIONS": {"location": str(tmp_path)},
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    }
    storages._storages.clear()
    storages.__dict__.pop("backends", None)
    media.clear_cache()
    yield tmp_path
    storages._storages.clear()
    storages.__dict__.pop("backends", None)
    media.clear_cache()
