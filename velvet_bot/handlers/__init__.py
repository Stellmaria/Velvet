from __future__ import annotations

from typing import Any

from velvet_bot.presentation.telegram.compat import install_legacy_compatibility

# Temporary compatibility bridge. It keeps historical direct imports working while
# the presentation package is separated from older modules.
install_legacy_compatibility()

__all__ = ("router",)


def __getattr__(name: str) -> Any:
    """Keep the historical `handlers.router` import without loading every handler."""
    if name != "router":
        raise AttributeError(name)

    from velvet_bot.presentation.telegram.router import get_root_router

    router = get_root_router()
    globals()[name] = router
    return router
