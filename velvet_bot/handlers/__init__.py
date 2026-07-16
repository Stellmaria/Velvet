from __future__ import annotations

from typing import Any

from velvet_bot.discussion_dashboard_compat import get_discussion_dashboard_compat
from velvet_bot.presentation.telegram.compat import install_legacy_compatibility

# Keep historical imports working while presentation code is separated from older
# modules. This bridge is installed here once; the composition root must not repeat it.
install_legacy_compatibility()
import velvet_bot.handlers.analytics_discussion_overrides as analytics_discussion_module

analytics_discussion_module._get_discussion_dashboard = get_discussion_dashboard_compat

__all__ = ("router",)


def __getattr__(name: str) -> Any:
    """Keep the historical `handlers.router` import without loading every handler."""
    if name != "router":
        raise AttributeError(name)

    from velvet_bot.presentation.telegram.router import get_root_router

    router = get_root_router()
    globals()[name] = router
    return router
