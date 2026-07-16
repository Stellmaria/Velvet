import logging

from aiogram import Router
from aiogram.types import ErrorEvent

import velvet_bot.multi_story_support as multi_story_support
from velvet_bot.multi_story_queries import list_assigned_character_stories

multi_story_support.list_assigned_character_stories = list_assigned_character_stories
multi_story_support.install_multi_story_support()

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.handlers.admin_directory import router as admin_directory_router
from velvet_bot.handlers.admin_media_display import router as admin_media_display_router
from velvet_bot.handlers.admin_media_spoiler import router as admin_media_spoiler_router
from velvet_bot.handlers.admin_stories import router as admin_stories_router
from velvet_bot.handlers.admin_uncategorized import router as admin_uncategorized_router
from velvet_bot.handlers.admin_universe_story_flow import (
    router as admin_universe_story_flow_router,
)
from velvet_bot.handlers.analytics_dashboard import router as analytics_dashboard_router
from velvet_bot.handlers.analytics_dashboard_overrides import (
    router as analytics_dashboard_overrides_router,
)
from velvet_bot.handlers.analytics_discussion_overrides import (
    router as analytics_discussion_overrides_router,
)
from velvet_bot.handlers.analytics_management import router as analytics_management_router
from velvet_bot.handlers.archive import router as archive_router
from velvet_bot.handlers.channel_analytics import router as channel_analytics_router
from velvet_bot.handlers.character_aliases import router as character_aliases_router
from velvet_bot.handlers.characters import router as characters_router
from velvet_bot.handlers.discussion_updates import router as discussion_updates_router
from velvet_bot.handlers.guest_archive import router as guest_archive_router
from velvet_bot.handlers.inline_help import router as inline_help_router
from velvet_bot.handlers.kr_profile_overrides import router as kr_profile_overrides_router
from velvet_bot.handlers.kr_universe_entry import router as kr_universe_entry_router
from velvet_bot.handlers.media_browser import router as media_browser_router
from velvet_bot.handlers.media_prompt_binding import router as media_prompt_binding_router
from velvet_bot.handlers.multi_story_kr import router as multi_story_kr_router
from velvet_bot.handlers.public_archive import router as public_archive_router
from velvet_bot.handlers.public_manager import router as public_manager_router
from velvet_bot.handlers.public_media_display import router as public_media_display_router
from velvet_bot.handlers.public_notification_open import (
    router as public_notification_open_router,
)
from velvet_bot.handlers.publication_center_safe import (
    router as publication_center_router,
)
from velvet_bot.handlers.quality_center import router as quality_center_router
from velvet_bot.handlers.quality_duplicates import router as quality_duplicates_router
from velvet_bot.handlers.reference_albums import router as reference_albums_router
from velvet_bot.handlers.reference_documents import router as reference_documents_router
from velvet_bot.handlers.reference_management import router as reference_management_router
from velvet_bot.handlers.references import router as references_router
from velvet_bot.handlers.spoiler_save import router as spoiler_save_router
from velvet_bot.handlers.start import router as start_router
from velvet_bot.handlers.telegram_analytics_import import (
    router as telegram_analytics_import_router,
)
from velvet_bot.safe_analytics_edit import install_safe_analytics_edit

install_safe_analytics_edit()

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


router.include_router(channel_analytics_router)
router.include_router(analytics_dashboard_overrides_router)
router.include_router(analytics_discussion_overrides_router)
router.include_router(analytics_management_router)
router.include_router(analytics_dashboard_router)
router.include_router(quality_duplicates_router)
router.include_router(quality_center_router)
router.include_router(character_aliases_router)
router.include_router(telegram_analytics_import_router)
router.include_router(discussion_updates_router)
router.include_router(start_router)
router.include_router(public_media_display_router)
router.include_router(kr_universe_entry_router)
router.include_router(kr_profile_overrides_router)
router.include_router(multi_story_kr_router)
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
# Publication commands must be before archive.py's catch-all topic handler.
router.include_router(publication_center_router)
router.include_router(archive_router)

__all__ = ("router",)
