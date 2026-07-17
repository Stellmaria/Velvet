from __future__ import annotations

import asyncio

_AI_LOCK: asyncio.Lock | None = None


def get_local_ai_lock() -> asyncio.Lock:
    """Return one process-wide lock for all local Ollama vision requests."""

    global _AI_LOCK
    if _AI_LOCK is None:
        _AI_LOCK = asyncio.Lock()
    return _AI_LOCK


__all__ = ("get_local_ai_lock",)
