from __future__ import annotations

import asyncio

_AI_LOCK: asyncio.Lock | None = None
_STORAGE_LIBRARIAN_ARCHIVE_PHASE_ENABLED = False


def get_local_ai_lock() -> asyncio.Lock:
    """Return one process-wide lock for all local Ollama vision requests."""

    global _AI_LOCK
    if _AI_LOCK is None:
        _AI_LOCK = asyncio.Lock()
    return _AI_LOCK


def set_storage_librarian_archive_phase_enabled(enabled: bool) -> None:
    """Expose the explicit Arthur full-archive phase to local inference workers."""

    global _STORAGE_LIBRARIAN_ARCHIVE_PHASE_ENABLED
    _STORAGE_LIBRARIAN_ARCHIVE_PHASE_ENABLED = bool(enabled)


def storage_librarian_archive_phase_enabled() -> bool:
    """Return whether Arthur currently owns the explicit full-archive phase."""

    return _STORAGE_LIBRARIAN_ARCHIVE_PHASE_ENABLED


__all__ = (
    "get_local_ai_lock",
    "set_storage_librarian_archive_phase_enabled",
    "storage_librarian_archive_phase_enabled",
)
