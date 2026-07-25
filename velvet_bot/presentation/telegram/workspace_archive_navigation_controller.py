from __future__ import annotations

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.workspace_archive_navigation import (
    replace_workspace_archive_page,
    send_workspace_archive_page,
)
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    WorkspacePersonalArchiveAction,
    WorkspacePersonalArchiveActionFilter,
)

_NAVIGATION_ACTIONS = frozenset({"open", "show", "close", "empty", "help"})


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _resolve_workspace_archive_access(
    *,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
    user_id: int,
    workspace_id: int,
) -> tuple[Workspace, bool]:
    global_owner = _is_global_owner(user_id)
    if workspace_id:
        workspace = await workspace_service.set_active_workspace(
            workspace_id=int(workspace_id),
            user_id=int(user_id),
            global_owner=global_owner,
        )
    else:
        workspace = await workspace_service.resolve_active_workspace(
            user_id=int(user_id),
            global_owner=global_owner,
        )
    membership = await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=int(user_id),
        minimum_role="viewer",
        global_owner=global_owner,
    )
    if workspace.is_system:
        raise WorkspaceAccessError(
            "Системный Velvet использует основной интерфейс Стэл, а не личный модуль."
        )
    if not await workspace_product_service.is_module_enabled(
        workspace_id=workspace.id,
        module_key="archive",
    ):
        raise WorkspaceAccessError("Модуль выключен или не разрешён Стэл.")
    return workspace, membership.role == "owner" or global_owner


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
        workspace, owner_access = await _resolve_workspace_archive_access(
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

    page = await get_archive_page(
        database,
        archive_action.character_id,
        archive_action.offset,
        workspace_id=workspace.id,
        include_adult_restricted=True,
        include_oversized_images=True,
    )
    if page is None:
        await callback.answer(
            "Персонаж не найден в этом пространстве.",
            show_alert=True,
        )
        return
    if page.media is None:
        await callback.answer("Архив персонажа пока пуст.", show_alert=True)
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
