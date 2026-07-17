from __future__ import annotations

import logging

from aiogram import Router
from aiogram.types import ErrorEvent

from velvet_bot.ai_quality_schema_compat import install_ai_quality_schema_compatibility
from velvet_bot.media_set_ui_compat import install_media_set_ui
from velvet_bot.owner_menu_compat import install_owner_menu_navigation
from velvet_bot.quality_calibration_dashboard import install_quality_calibration_dashboard
from velvet_bot.quality_calibration_ui import install_quality_calibration_report_ui
from velvet_bot.quality_set_ai_dashboard import install_set_consistency_dashboard

logger = logging.getLogger(__name__)
_ROOT_ROUTER: Router | None = None


def _build_root_router() -> Router:
    install_ai_quality_schema_compatibility()
    install_set_consistency_dashboard()
    install_quality_calibration_dashboard()

    # Install corrected media-set compatibility before handlers bind functions.
    import velvet_bot.media_set_duplicate_actions  # noqa: F401
    import velvet_bot.media_set_ai_discovery  # noqa: F401

    install_media_set_ui()
    install_owner_menu_navigation()

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
    from velvet_bot.handlers.ai_jobs import router as ai_jobs_router
    from velvet_bot.handlers.analytics_dashboard import router as analytics_dashboard_router
    from velvet_bot.handlers.analytics_dashboard_overrides import (
        router as analytics_dashboard_overrides_router,
    )
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
    from velvet_bot.handlers.error_center import router as error_center_router
    from velvet_bot.handlers.guest_archive import router as guest_archive_router
    from velvet_bot.handlers.inline_help import router as inline_help_router
    from velvet_bot.handlers.kr_profile_overrides import router as kr_profile_overrides_router
    from velvet_bot.handlers.kr_universe_entry import router as kr_universe_entry_router
    from velvet_bot.handlers.media_browser import router as media_browser_router
    from velvet_bot.handlers.media_prompt_binding import router as media_prompt_binding_router
    from velvet_bot.handlers.multi_story_kr import router as multi_story_kr_router
    from velvet_bot.handlers.owner_actions import router as owner_actions_router
    from velvet_bot.handlers.owner_menu import router as owner_menu_router
    from velvet_bot.handlers.public_archive import router as public_archive_router
    from velvet_bot.handlers.public_manager import router as public_manager_router
    from velvet_bot.handlers.public_media_display import router as public_media_display_router
    from velvet_bot.handlers.public_notification_open import (
        router as public_notification_open_router,
    )
    from velvet_bot.handlers.publication_center_safe import (
        router as publication_center_router,
    )
    from velvet_bot.handlers.quality_ai import router as quality_ai_router
    from velvet_bot.handlers.quality_ai_preview import router as quality_ai_preview_router
    from velvet_bot.handlers.quality_calibration import router as quality_calibration_router
    from velvet_bot.handlers.quality_center import router as quality_center_router
    from velvet_bot.handlers.quality_duplicates import router as quality_duplicates_router
    from velvet_bot.handlers.quality_operations import router as quality_operations_router
    from velvet_bot.handlers.quality_set_ai import router as quality_set_ai_router
    from velvet_bot.handlers.quality_sets import router as quality_sets_router
    from velvet_bot.handlers.reference_albums import router as reference_albums_router
    from velvet_bot.handlers.reference_comparison import router as reference_comparison_router
    from velvet_bot.handlers.reference_comparison_help import (
        router as reference_comparison_help_router,
    )
    from velvet_bot.handlers.reference_documents import router as reference_documents_router
    from velvet_bot.handlers.reference_management import router as reference_management_router
    from velvet_bot.handlers.references import router as references_router
    from velvet_bot.handlers.spoiler_save import router as spoiler_save_router
    from velvet_bot.handlers.start import router as start_router
    from velvet_bot.handlers.supervisor_control import router as supervisor_control_router
    from velvet_bot.handlers.system_center import router as system_center_router
    from velvet_bot.handlers.telegram_analytics_import import (
        router as telegram_analytics_import_router,
    )
    from velvet_bot.handlers.velvet_ai import router as velvet_ai_router
    from velvet_bot.handlers.velvet_ai_formatting import router as velvet_ai_formatting_router
    from velvet_bot.handlers.velvet_ai_visual import router as velvet_ai_visual_router

    install_quality_calibration_report_ui()

    root = Router(name="velvet_bot.presentation.telegram")

    @root.error()
    async def handle_unhandled_error(event: ErrorEvent) -> bool:
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

    root.include_router(error_center_router)
    root.include_router(owner_actions_router)
    root.include_router(owner_menu_router)
    root.include_router(supervisor_control_router)
    root.include_router(system_center_router)
    root.include_router(channel_analytics_router)
    root.include_router(analytics_dashboard_overrides_router)
    root.include_router(analytics_discussion_overrides_router)
    root.include_router(analytics_management_router)
    root.include_router(analytics_dashboard_router)
    root.include_router(backup_center_router)
    root.include_router(ai_jobs_router)
    root.include_router(quality_operations_router)
    root.include_router(velvet_ai_formatting_router)
    root.include_router(velvet_ai_visual_router)
    root.include_router(velvet_ai_router)
    root.include_router(quality_duplicates_router)
    root.include_router(quality_sets_router)
    root.include_router(quality_set_ai_router)
    root.include_router(quality_calibration_router)
    root.include_router(quality_ai_preview_router)
    root.include_router(quality_ai_router)
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
    root.include_router(reference_comparison_help_router)
    root.include_router(reference_comparison_router)
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
