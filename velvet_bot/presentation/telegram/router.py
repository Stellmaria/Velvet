from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.discussion_dashboard_compat import get_discussion_dashboard_compat
from velvet_bot.media_set_ui_compat import install_media_set_ui
from velvet_bot.presentation.telegram.compat import install_legacy_compatibility

logger = logging.getLogger(__name__)
_ROOT_ROUTER: Router | None = None


def _build_root_router() -> Router:
    install_legacy_compatibility()

    # Install corrected media-set compatibility before handlers bind functions.
    import velvet_bot.media_set_duplicate_actions  # noqa: F401
    import velvet_bot.media_set_ai_discovery  # noqa: F401

    install_media_set_ui()

    from velvet_bot.handlers.admin_directory import router as admin_directory_router
    from velvet_bot.handlers.admin_large_media_preview import (
        router as admin_large_media_preview_router,
    )
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
    import velvet_bot.handlers.analytics_discussion_overrides as analytics_discussion_module
    from velvet_bot.handlers.analytics_discussion_overrides import (
        router as analytics_discussion_overrides_router,
    )
    from velvet_bot.handlers.analytics_management import router as analytics_management_router
    from velvet_bot.handlers.archive import router as archive_router
    from velvet_bot.handlers.backup_center import router as backup_center_router
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
    from velvet_bot.handlers.quality_sets import router as quality_sets_router
    from velvet_bot.handlers.reference_albums import router as reference_albums_router
    from velvet_bot.handlers.reference_documents import router as reference_documents_router
    from velvet_bot.handlers.reference_management import router as reference_management_router
    from velvet_bot.handlers.references import router as references_router
    from velvet_bot.handlers.spoiler_save import router as spoiler_save_router
    from velvet_bot.handlers.start import router as start_router
    from velvet_bot.handlers.system_center import router as system_center_router
    from velvet_bot.handlers.telegram_analytics_import import (
        router as telegram_analytics_import_router,
    )

    analytics_discussion_module._get_discussion_dashboard = get_discussion_dashboard_compat

    root = Router(name="velvet_bot.presentation.telegram")

    @root.error()
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

    root.include_router(system_center_router)
    root.include_router(channel_analytics_router)
    root.include_router(analytics_dashboard_overrides_router)
    root.include_router(analytics_discussion_overrides_router)
    root.include_router(analytics_management_router)
    root.include_router(analytics_dashboard_router)
    root.include_router(backup_center_router)
    root.include_router(quality_duplicates_router)
    root.include_router(quality_sets_router)
    root.include_router(quality_center_router)
    root.include_router(character_aliases_router)
    root.include_router(telegram_analytics_import_router)
    root.include_router(discussion_updates_router)
    root.include_router(start_router)
    root.include_router(public_media_display_router)
    root.include_router(kr_universe_entry_router)
    root.include_router(kr_profile_overrides_router)
    root.include_router(multi_story_kr_router)
    root.include_router(public_manager_router)
    root.include_router(public_notification_open_router)
    root.include_router(public_archive_router)
    root.include_router(media_prompt_binding_router)
    root.include_router(admin_media_spoiler_router)
    root.include_router(admin_large_media_preview_router)
    root.include_router(admin_media_display_router)
    root.include_router(admin_stories_router)
    root.include_router(admin_universe_story_flow_router)
    root.include_router(admin_uncategorized_router)
    root.include_router(admin_directory_router)
    root.include_router(characters_router)
    root.include_router(media_browser_router)
    root.include_router(reference_documents_router)
    root.include_router(reference_albums_router)
    root.include_router(reference_management_router)
    root.include_router(references_router)
    root.include_router(inline_help_router)
    root.include_router(guest_archive_router)
    root.include_router(spoiler_save_router)
    # Publication commands must be before archive.py's catch-all topic handler.
    root.include_router(publication_center_router)
    root.include_router(archive_router)
    return root


def get_root_router() -> Router:
    global _ROOT_ROUTER
    if _ROOT_ROUTER is None:
        _ROOT_ROUTER = _build_root_router()
    return _ROOT_ROUTER


__all__ = ("get_root_router",)
