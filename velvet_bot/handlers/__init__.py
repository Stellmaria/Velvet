import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.handlers.archive import router as archive_router
from velvet_bot.handlers.characters import router as characters_router
from velvet_bot.handlers.guest_archive import router as guest_archive_router
from velvet_bot.handlers.inline_help import router as inline_help_router
from velvet_bot.handlers.media_browser import router as media_browser_router
from velvet_bot.handlers.reference_management import router as reference_management_router
from velvet_bot.handlers.references import router as references_router
from velvet_bot.handlers.start import router as start_router

logger = logging.getLogger(__name__)
router = Router(name=__name__)


@router.error()
async def handle_unhandled_error(
    event: ErrorEvent,
    audit_logger: TelegramAuditLogger | None = None,
) -> bool:
    logger.critical(
        "Unhandled bot error: %s",
        event.exception,
        exc_info=(
            type(event.exception),
            event.exception,
            event.exception.__traceback__,
        ),
    )
    if audit_logger is not None:
        await audit_logger.error(
            "Необработанная ошибка бота",
            event.exception,
            update_id=event.update.update_id,
            exception_type=type(event.exception).__name__,
        )
    return True


router.include_router(start_router)
router.include_router(characters_router)
router.include_router(media_browser_router)
router.include_router(reference_management_router)
router.include_router(references_router)
router.include_router(inline_help_router)
router.include_router(guest_archive_router)
router.include_router(archive_router)

__all__ = ("router",)
