from __future__ import annotations

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.workspace_archive_access import (
    load_workspace_archive_action_page,
    resolve_workspace_archive_access,
)
from velvet_bot.presentation.telegram.workspace_archive_navigation import (
    replace_workspace_archive_page,
    send_workspace_archive_page,
)
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    WorkspacePersonalArchiveAction,
    WorkspacePersonalArchiveActionFilter,
)

_NAVIGATION_ACTIONS = frozenset({"open", "show", "close", "empty", "help"})


async def handle_workspace_archive_navigation(
    callback: CallbackQuery,
    archive_action: WorkspacePersonalArchiveAction,
    database: Database,
    bot: Bot,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    action = archive_action.action
    if action == "close":
        if isinstance(callback.message, Message):
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        await callback.answer()
        return

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

    if action == "empty":
        await callback.answer(
            "У этого персонажа пока нет материалов. Сохраните их командой /save.",
            show_alert=True,
        )
        return
    if action == "help":
        await callback.answer(
            "Выберите персонажа кнопкой «Сохранить», затем присылайте несколько "
            "фото, видео или документов подряд. После последнего файла нажмите "
            "«Завершить загрузку».",
            show_alert=True,
        )
        return

    page = await load_workspace_archive_action_page(
        callback,
        archive_action,
        database,
        workspace=workspace,
        validate_media_id=False,
    )
    if page is None or page.media is None:
        return

    if action == "open":
        if not isinstance(callback.message, Message):
            await callback.answer("Не удалось определить чат.", show_alert=True)
            return
        try:
            await send_workspace_archive_page(
                bot,
                database=database,
                workspace_product_service=workspace_product_service,
                chat_id=callback.message.chat.id,
                user_id=callback.from_user.id,
                workspace_id=workspace.id,
                page=page,
                owner_access=owner_access,
            )
        except TelegramAPIError:
            await callback.answer(
                "Telegram больше не может открыть этот файл.",
                show_alert=True,
            )
            return
        await callback.answer()
        return

    await replace_workspace_archive_page(
        callback,
        bot,
        database=database,
        workspace_product_service=workspace_product_service,
        user_id=callback.from_user.id,
        workspace_id=workspace.id,
        page=page,
        owner_access=owner_access,
    )


def register_workspace_archive_navigation(router: Router) -> None:
    router.callback_query.register(
        handle_workspace_archive_navigation,
        WorkspacePersonalArchiveActionFilter(*sorted(_NAVIGATION_ACTIONS)),
    )


__all__ = (
    "handle_workspace_archive_navigation",
    "register_workspace_archive_navigation",
)
