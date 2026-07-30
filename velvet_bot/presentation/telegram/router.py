from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent, Message

from velvet_bot.domains.auf_wallet import AufPriceNotConfigured, AufWalletError
from velvet_bot.infrastructure.transient_connections import (
    is_transient_connection_error,
)
from velvet_bot.presentation.telegram.compat import (
    install_post_router_compatibility,
    install_pre_router_compatibility,
)

logger = logging.getLogger(__name__)
_ROOT_ROUTER: Router | None = None
_TELEGRAM_TRANSPORT_MARKERS = (
    "api.telegram.org",
    "telegramnetworkerror",
    "http client says",
)


def _is_transient_telegram_error(error: BaseException) -> bool:
    message = " ".join(str(error).casefold().split())
    return is_transient_connection_error(error) and any(
        marker in message for marker in _TELEGRAM_TRANSPORT_MARKERS
    )


async def _show_auf_charging_error(event: ErrorEvent) -> bool:
    message = str(event.exception).strip() or "Не удалось рассчитать стоимость в Ауф."
    callback = event.update.callback_query
    if callback is not None:
        await callback.answer(message, show_alert=True)
        return True
    update_message = event.update.message
    if isinstance(update_message, Message):
        await update_message.answer(message)
        return True
    return False


def _build_root_router() -> Router:
    install_pre_router_compatibility()

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
    from velvet_bot.presentation.telegram.routers.user_management import (
        router as user_management_router,
    )

    install_post_router_compatibility()

    root = Router(name="velvet_bot.presentation.telegram")

    @root.error()
    async def handle_unhandled_error(event: ErrorEvent) -> bool:
        if isinstance(event.exception, (AufWalletError, AufPriceNotConfigured)):
            if await _show_auf_charging_error(event):
                return True
        if _is_transient_telegram_error(event.exception):
            logger.info(
                "Transient Telegram connection error recovered: %s",
                event.exception,
            )
            return True
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

    root.include_router(user_management_router)
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
