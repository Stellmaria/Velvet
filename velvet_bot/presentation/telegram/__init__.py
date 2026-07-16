from __future__ import annotations

from typing import Any

__all__ = ("get_root_router",)


def __getattr__(name: str) -> Any:
    if name != "get_root_router":
        raise AttributeError(name)

    from velvet_bot.presentation.telegram.router import get_root_router

    globals()[name] = get_root_router
    return get_root_router
