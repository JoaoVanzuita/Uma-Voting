"""Seleção do armazenamento de mídia (filesystem ou S3 compatível)."""

from __future__ import annotations

import functools
from pathlib import Path

from django.core.files.storage import Storage, storages
from django.core.files.uploadedfile import SimpleUploadedFile


class MediaStorageError(Exception):
    """Falha ao ler, gravar ou listar um arquivo de mídia."""


def get_storage() -> Storage:
    """Storage configurado em ``STORAGES["default"]``."""
    return storages["default"]


def exists(name: str) -> bool:
    return get_storage().exists(name)


def read_bytes(name: str) -> bytes:
    """Lê o arquivo inteiro; falha de leitura vira ``MediaStorageError``."""
    try:
        with get_storage().open(name, "rb") as handle:
            return handle.read()
    except (FileNotFoundError, OSError) as exc:
        raise MediaStorageError("Arquivo não encontrado no storage.") from exc


def save_bytes(name: str, data: bytes, *, content_type: str) -> str:
    """Grava bytes em ``name`` e devolve o nome salvo.

    Chaves de imagem são content-addressed (``characters/<id>/<sha256>.webp``),
    então reescrever o mesmo caminho significa regravar o mesmo conteúdo e o
    storage não deve acrescentar sufixo (``file_overwrite`` no S3).
    """
    return get_storage().save(
        name,
        SimpleUploadedFile(name, data, content_type=content_type),
        max_length=255,
    )


def asset_url(file_path: str) -> str:
    """URL da imagem (assinada quando o storage é S3) ou ``""`` em caso de falha."""
    if not file_path:
        return ""
    try:
        return get_storage().url(file_path)
    except Exception:  # noqa: BLE001 - URL quebrada vira placeholder no template
        return ""


def _walk(prefix: str) -> list[str]:
    storage = get_storage()
    found: list[str] = []
    try:
        directories, files = storage.listdir(prefix)
    except FileNotFoundError, NotImplementedError, OSError:
        return found

    for name in files:
        found.append(f"{prefix}/{name}" if prefix else name)
    for directory in directories:
        found.extend(_walk(f"{prefix}/{directory}" if prefix else directory))
    return found


@functools.lru_cache(maxsize=8)
def _character_objects_cached(signature: str, root: str) -> tuple[str, ...]:
    return tuple(sorted(_walk(root)))


_CHARACTERS_ROOT = "characters"


def list_character_objects(refresh: bool = False) -> list[str]:
    """Lista, em uma única passada, todos os objetos sob ``characters/``."""
    storage = get_storage()
    signature = f"{type(storage).__qualname__}|{getattr(storage, 'location', '')}"
    if refresh:
        _character_objects_cached.cache_clear()
    return list(_character_objects_cached(signature, _CHARACTERS_ROOT))


def clear_cache() -> None:
    """Invalida a listagem em cache (usado em testes e após importações)."""
    _character_objects_cached.cache_clear()


def local_root() -> Path | None:
    """Raiz local do storage, ou ``None`` quando os arquivos vivem no S3."""
    location = getattr(get_storage(), "location", None)
    return Path(location) if location is not None else None
