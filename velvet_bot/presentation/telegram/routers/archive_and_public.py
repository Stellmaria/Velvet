from __future__ import annotations

from aiogram import F, Router

from velvet_bot.domains.watermark.workspace_template_runtime import (
    install_workspace_watermark_templates,
)
from velvet_bot.presentation.telegram.public_archive_rework import (
    register_public_archive_rework,
)
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers.telegram_analytics_import import (
    router as telegram_analytics_import_router,
)
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers.discussion_updates import (
    router as discussion_updates_router,
)
from velvet_bot.presentation.telegram.routers.workspace_guided_actions import (
    router as workspace_guided_actions_router,
)
from velvet_bot.presentation.telegram.routers.workspace_character_pickers import (
    router as workspace_character_pickers_router,
)
from velvet_bot.presentation.telegram.routers.workspace_character_topic_creation import (
    router as workspace_character_topic_creation_router,
)
from velvet_bot.presentation.telegram.routers.workspace_character_management import (
    router as workspace_character_management_router,
)
from velvet_bot.presentation.telegram.routers.workspace_onboarding_channel_bind import (
    router as workspace_onboarding_channel_bind_router,
)
from velvet_bot.presentation.telegram.routers.workspace_onboarding import (
    router as workspace_onboarding_router,
)
from velvet_bot.presentation.telegram.routers.workspace_reference_library import (
    router as workspace_reference_library_router,
)
from velvet_bot.presentation.telegram.routers.workspace_publications import (
    entry_router as workspace_publication_entry_router,
    router as workspace_publications_router,
)
from velvet_bot.presentation.telegram.routers.workspace_admin import (
    router as workspace_admin_router,
)
from velvet_bot.presentation.telegram.routers.workspace_team import (
    router as workspace_team_router,
)
from velvet_bot.presentation.telegram.routers.workspace_taxonomy_admin import (
    router as workspace_taxonomy_admin_router,
)
from velvet_bot.presentation.telegram.routers.workspace_watermark_archive_only import (
    router as workspace_watermark_archive_only_router,
)
from velvet_bot.presentation.telegram.routers.workspace_watermark_templates import (
    router as workspace_watermark_templates_router,
)
from velvet_bot.presentation.telegram.routers.workspace_watermark import (
    router as workspace_watermark_router,
)
from velvet_bot.presentation.telegram.routers.workspace_owner_controls import (
    router as workspace_owner_controls_router,
)
from velvet_bot.presentation.telegram.routers.workspaces import (
    router as workspaces_router,
)
from velvet_bot.presentation.telegram.routers.workspace_reference_buttons import (
    router as workspace_reference_buttons_router,
)
from velvet_bot.presentation.telegram.workspace_ui_adjustments import (
    apply_workspace_ui_adjustments,
)
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers.start import (
    router as start_router,
)
from velvet_bot.presentation.telegram.routers.public_archive.media_display import (
    router as public_media_display_router,
)
from velvet_bot.presentation.telegram.routers.characters.aliases import (
    router as character_aliases_router,
)
from velvet_bot.presentation.telegram.routers.characters.game_universes import (
    router as game_universes_router,
)
from velvet_bot.presentation.telegram.routers.stories.kr_universe_entry import (
    router as kr_universe_entry_router,
)
from velvet_bot.presentation.telegram.routers.characters.kr_profile_overrides import (
    router as kr_profile_overrides_router,
)
from velvet_bot.presentation.telegram.routers.stories.multi_story_kr import (
    router as multi_story_kr_router,
)
from velvet_bot.presentation.telegram.routers.public_archive.manager import (
    router as public_manager_router,
)
from velvet_bot.presentation.telegram.routers.public_archive.notification_open import (
    router as public_notification_open_router,
)
from velvet_bot.presentation.telegram.routers.public_archive.catalog import (
    router as public_archive_router,
)
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers.media_prompt_binding import (
    router as media_prompt_binding_router,
)
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers.admin_media_spoiler import (
    router as admin_media_spoiler_router,
)
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers.admin_large_media_preview import (
    router as admin_large_media_preview_router,
)
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers.admin_media_display import (
    router as admin_media_display_router,
)
from velvet_bot.presentation.telegram.routers.stories.management import (
    router as admin_stories_router,
)
from velvet_bot.presentation.telegram.routers.stories.universe_flow import (
    router as admin_universe_story_flow_router,
)
from velvet_bot.presentation.telegram.routers.characters.uncategorized import (
    router as admin_uncategorized_router,
)
from velvet_bot.presentation.telegram.routers.characters.rename import (
    router as character_rename_router,
)
from velvet_bot.presentation.telegram.routers.characters.directory import (
    router as admin_directory_router,
)
from velvet_bot.presentation.telegram.routers.characters.profiles import (
    router as characters_router,
)
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers.media_browser import (
    router as media_browser_router,
)
from velvet_bot.presentation.telegram.routers.references.comparison_help import (
    router as reference_comparison_help_router,
)
from velvet_bot.presentation.telegram.routers.references.comparison import (
    router as reference_comparison_router,
)
from velvet_bot.presentation.telegram.routers.references.documents import (
    router as reference_documents_router,
)
from velvet_bot.presentation.telegram.routers.references.albums import (
    router as reference_albums_router,
)
from velvet_bot.presentation.telegram.routers.references.management import (
    router as reference_management_router,
)
from velvet_bot.presentation.telegram.routers.references.catalog import (
    router as references_router,
)
from velvet_bot.presentation.telegram.routers.archive_and_public_controllers.inline_help import (
    router as inline_help_router,
)
from velvet_bot.presentation.telegram.routers.archive.guest import (
    router as guest_archive_router,
)
from velvet_bot.presentation.telegram.routers.archive.spoiler import (
    router as spoiler_save_router,
)
from velvet_bot.presentation.telegram.routers.publication.safe import (
    router as publication_center_router,
)
from velvet_bot.presentation.telegram.save_mode_runtime import (
    install_save_command_modes,
    register_save_mode_handlers,
)

install_save_command_modes()

from velvet_bot.presentation.telegram.routers.archive.save import (
    PendingSaveUploadFilter,
    handle_pending_save_upload,
    router as archive_router,
)

install_workspace_watermark_templates()
apply_workspace_ui_adjustments()

router = Router(name=__name__)
# Bundle-level handlers run before child routers. Any active single or set save
# session must therefore win before broad reference photo/document handlers.
router.message.register(
    handle_pending_save_upload,
    F.photo | F.video | F.animation | F.document,
    PendingSaveUploadFilter(),
)
# `/save` without attached media opens one-file mode, while `/save_set` opens a
# batch. Register this on the existing bundle instead of adding another router.
register_save_mode_handlers(router)
register_public_archive_rework(router)
router.include_router(character_aliases_router)
router.include_router(telegram_analytics_import_router)
router.include_router(discussion_updates_router)
# `/start` is deliberately before all workspace form routers: it is the visible
# recovery action when a previous button or upload session was interrupted.
router.include_router(start_router)
# Workspace onboarding must intercept the first workspace-name FSM response before
# the legacy workspace router and must own setup/binding commands before broad handlers.
router.include_router(workspace_onboarding_channel_bind_router)
router.include_router(workspace_onboarding_router)
# Workspace policy commands, callbacks and FSM forms must run before broad
# owner/archive controllers. Inline pickers and automatic topic creation must
# intercept the personal character module before its broad text-command handler.
router.include_router(workspace_taxonomy_admin_router)
router.include_router(workspace_guided_actions_router)
router.include_router(workspace_character_pickers_router)
router.include_router(workspace_character_topic_creation_router)
router.include_router(workspace_character_management_router)
# Personal Qwen, scoped rework/public callbacks and its FSM must win before the
# older reference-only Qwen entry and before generic owner archive callbacks.
router.include_router(workspace_watermark_archive_only_router)
# Button-first reference management must intercept personal reference cards and
# replacement uploads before the command-compatible reference router.
router.include_router(workspace_reference_buttons_router)
router.include_router(workspace_reference_library_router)
router.include_router(workspace_admin_router)
router.include_router(workspace_team_router)
router.include_router(workspace_watermark_templates_router)
router.include_router(workspace_watermark_router)
router.include_router(workspace_owner_controls_router)
# The tenant publication entry must precede generic `wsp:module` help. The
# publication capture router remains below reference/save flows.
router.include_router(workspace_publication_entry_router)
router.include_router(workspaces_router)
router.include_router(public_media_display_router)
# Virtual universe groups must run before generic setuni/puni/menu handlers.
router.include_router(game_universes_router)
router.include_router(kr_universe_entry_router)
router.include_router(kr_profile_overrides_router)
router.include_router(multi_story_kr_router)
router.include_router(public_manager_router)
router.include_router(public_notification_open_router)
router.include_router(public_archive_router)
router.include_router(media_prompt_binding_router)
router.include_router(admin_media_spoiler_router)
router.include_router(admin_large_media_preview_router)
router.include_router(admin_media_display_router)
router.include_router(admin_stories_router)
router.include_router(admin_universe_story_flow_router)
router.include_router(admin_uncategorized_router)
router.include_router(character_rename_router)
router.include_router(admin_directory_router)
router.include_router(characters_router)
router.include_router(media_browser_router)
router.include_router(reference_comparison_help_router)
router.include_router(reference_comparison_router)
router.include_router(reference_documents_router)
router.include_router(reference_albums_router)
router.include_router(reference_management_router)
router.include_router(references_router)
router.include_router(inline_help_router)
router.include_router(guest_archive_router)
router.include_router(spoiler_save_router)
# Personal publication capture stays after reference/save handlers, but before
# the legacy system publication center and archive catch-all.
router.include_router(workspace_publications_router)
router.include_router(publication_center_router)
router.include_router(archive_router)

__all__ = ("router",)
