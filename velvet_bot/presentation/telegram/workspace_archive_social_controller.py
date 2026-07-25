from __future__ import annotations

from aiogram import Bot, Router
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.media_preferences import (
    WorkspaceMediaPreferenceRepository,
)
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.public_catalog import toggle_character_subscription, toggle_public_like
from velvet_bot.presentation.telegram.workspace_archive_access import (
    load_workspace_archive_action_page,
    resolve_workspace_archive_access,
)
from velvet_bot.presentation.telegram.workspace_archive_navigation import (
    replace_workspace_archive_page,
)
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    WorkspacePersonalArchiveAction,
    WorkspacePersonalArchiveActionFilter,
)

_SOCIAL_ACTIONS = frozenset({"like", "sub"})


async def handle_workspace_archive_social_action(
    callback: CallbackQuery,
    archive_action: WorkspacePersonalArchiveAction,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace, owner_access = await resolve_workspace_archive_access(
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=archive_action.workspace_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    if not owner_access:
        await callback.answer(
            "Эта кнопка доступна только владельцу пространства.",
            show_alert=True,
        )
        return

    page = await load_workspace_archive_action_page(
        callback,
        archive_action,
        database,
        workspace=workspace,
    )
    if page is None or page.media is None:
        return

    if archive_action.action == "like":
        settings = await workspace_product_service.get_settings(workspace.id)
        if not settings.public_archive_enabled or not page.media.is_public:
            liked = await WorkspaceMediaPreferenceRepository(database).toggle_favorite(
                workspace_id=workspace.id,
                character_id=page.character.id,
                media_id=page.media.id,
                user_id=callback.from_user.id,
            )
            result_text = (
                "Личная отметка поставлена. Она не входит в публичные лайки."
                if liked
                else "Личная отметка снята."
            )
        else:
            liked, _ = await toggle_public_like(
                database,
                character_id=page.character.id,
                media_id=page.media.id,
                user_id=callback.from_user.id,
                workspace_id=workspace.id,
            )
            result_text = "Лайк поставлен." if liked else "Лайк снят."
    else:
        subscribed = await toggle_character_subscription(
            database,
            character_id=page.character.id,
            user_id=callback.from_user.id,
            workspace_id=workspace.id,
        )
        result_text = "Подписка включена." if subscribed else "Подписка отключена."

    await replace_workspace_archive_page(
        callback,
        bot,
        database=database,
        workspace_product_service=workspace_product_service,
        user_id=callback.from_user.id,
        workspace_id=workspace.id,
        page=page,
        owner_access=True,
    )
    if isinstance(callback.message, Message):
        await callback.message.answer(result_text)


def register_workspace_archive_social_actions(router: Router) -> None:
    router.callback_query.register(
        handle_workspace_archive_social_action,
        WorkspacePersonalArchiveActionFilter(*sorted(_SOCIAL_ACTIONS)),
    )


__all__ = (
    "handle_workspace_archive_social_action",
    "register_workspace_archive_social_actions",
)
