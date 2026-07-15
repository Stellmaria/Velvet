import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.handlers.admin_directory import router as admin_directory_router
from velvet_bot.handlers.admin_media_display import router as admin_media_display_router
from velvet_bot.handlers.admin_media_spoiler import router as admin_media_spoiler_router
from velvet_bot.handlers.admin_stories import router as admin_stories_router
from velvet_bot.handlers.admin_uncategorized import router as admin_uncategorized_router
from velvet_bot.handlers.admin_universe_story_flow import (
    router as admin_universe_story_flow_router,
)
from velvet_bot.handlers.archive import router as archive_router
from velvet_bot.handlers.characters import router as characters_router
from velvet_bot.handlers.guest_archive import router as guest_archive_router
from velvet_bot.handlers.inline_help import router as inline_help_router
from velvet_bot.handlers.media_browser import router as media_browser_router
from velvet_bot.handlers.media_prompt_binding import router as media_prompt_binding_router
from velvet_bot.handlers.public_archive import router as public_archive_router
from velvet_bot.handlers.public_manager import router as public_manager_router
from velvet_bot.handlers.public_media_display import router as public_media_display_router
from velvet_bot.handlers.public_notification_open import (
    router as public_notification_open_router,
)
from velvet_bot.handlers.reference_albums import router as reference_albums_router
from velvet_bot.handlers.reference_documents import router as reference_documents_router
from velvet_bot.handlers.reference_management import router as reference_management_router
from velvet_bot.handlers.references import router as references_router
from velvet_bot.handlers.spoiler_save import router as spoiler_save_router
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
router.include_router(public_media_display_router)
router.include_router(public_manager_router)
router.include_router(public_notification_open_router)
router.include_router(public_archive_router)
router.include_router(media_prompt_binding_router)
router.include_router(admin_media_spoiler_router)
router.include_router(admin_media_display_router)
router.include_router(admin_stories_router)
router.include_router(admin_universe_story_flow_router)
router.include_router(admin_uncategorized_router)
router.include_router(admin_directory_router)
router.include_router(characters_router)
router.include_router(media_browser_router)
router.include_router(reference_documents_router)
router.include_router(reference_albums_router)
router.include_router(reference_management_router)
router.include_router(references_router)
router.include_router(inline_help_router)
router.include_router(guest_archive_router)
router.include_router(spoiler_save_router)
router.include_router(archive_router)

__all__ = ("router",)
