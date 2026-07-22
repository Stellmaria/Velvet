from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from velvet_bot.infrastructure.transient_connections import (
    is_transient_connection_error,
)

from velvet_bot.presentation.telegram.compat import (
    install_post_router_compatibility,
    install_pre_router_compatibility,
)

logger = logging.getLogger(__name__)
_ROOT_ROUTER: Router | None = None


def _build_root_router() -> Router:
    install_pre_router_compatibility()

    # Import domain bundles only after pre-import compatibility has adapted legacy
    # bindings. The root composition boundary no longer knows individual handlers.
    from velvet_bot.presentation.telegram.routers.analytics import (
        router as analytics_router,
    )
    from velvet_bot.presentation.telegram.routers.archive_and_public import (
        router as archive_and_public_router,
    )
    from velvet_bot.presentation.telegram.routers.core_operations import (
        router as core_operations_router,
    )
    from velvet_bot.presentation.telegram.routers.quality_operations import (
        router as quality_operations_router,
    )

    install_post_router_compatibility()

    root = Router(name="velvet_bot.presentation.telegram")

    @root.error()
    async def handle_unhandled_error(event: ErrorEvent) -> bool:
        if is_transient_connection_error(event.exception):
            logger.info(
                "Transient Telegram connection error recovered: %s",
                event.exception,
            )
            return True
        # The root logging handler forwards this record, traceback included, to the
        # persistent incident center. Do not send a second audit message here.
        logger.critical(
            "Unhandled bot error: %s",
            event.exception,
            exc_info=(
                type(event.exception),
                event.exception,
                event.exception.__traceback__,
            ),
        )
        return True

    # Bundle order preserves the historical handler priority. Individual routers
    # remain ordered inside each bundle, including publication before archive's
    # catch-all topic handler.
    root.include_router(core_operations_router)
    root.include_router(analytics_router)
    root.include_router(quality_operations_router)
    root.include_router(archive_and_public_router)
    return root


def get_root_router() -> Router:
    global _ROOT_ROUTER
    if _ROOT_ROUTER is None:
        _ROOT_ROUTER = _build_root_router()
    return _ROOT_ROUTER


__all__ = ("get_root_router",)
