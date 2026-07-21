from __future__ import annotations

from importlib import import_module
from typing import Final, cast

from velvet_bot.domains.archive.models import ArchivePage, ArchivedMedia, DeletedArchiveItem
from velvet_bot.domains.archive.preview_models import PreviewPayload, PreviewRecord

_RUNTIME_EXPORTS: Final[dict[str, tuple[str, str]]] = {
    "ArchivePreviewRepository": (
        "velvet_bot.domains.archive.preview_repository",
        "ArchivePreviewRepository",
    ),
    "ArchiveRepository": (
        "velvet_bot.domains.archive.repository",
        "ArchiveRepository",
    ),
    "ArchiveService": (
        "velvet_bot.domains.archive.service",
        "ArchiveService",
    ),
}

__all__ = (
    "ArchivePage",
    "ArchivePreviewRepository",
    "ArchiveRepository",
    "ArchiveService",
    "ArchivedMedia",
    "DeletedArchiveItem",
    "PreviewPayload",
    "PreviewRecord",
)


def __getattr__(name: str) -> object:
    target = _RUNTIME_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = target
    value = cast(object, getattr(import_module(module_name), attribute_name))
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
