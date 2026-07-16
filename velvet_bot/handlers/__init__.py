from __future__ import annotations

from typing import Any

__all__ = ("router",)


def __getattr__(name: str) -> Any:
    """Keep the historical `handlers.router` import without eager side effects."""
    if name != "router":
        raise AttributeError(name)

    from velvet_bot.presentation.telegram.router import get_root_router

    router = get_root_router()
    globals()[name] = router
    return router
