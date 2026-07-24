from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Filter
from aiogram.types import CallbackQuery, Message

from velvet_bot.character_resolution import load_character_by_id
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.routers.references.albums import (
    send_reference_collection,
)
from velvet_bot.presentation.telegram.workspace_reference_dashboard import (
    WorkspaceReferenceAction,
    build_workspace_reference_dashboard,
    parse_workspace_reference_callback,
)
from velvet_bot.reference_catalog import list_character_references
from velvet_bot.workspace_ui import WorkspaceCallback


class WorkspaceReferenceActionFilter(Filter):
    async def __call__(
        self,
        callback: CallbackQuery,
    ) -> bool | dict[str, WorkspaceReferenceAction]:
        reference_action = parse_workspace_reference_callback(callback.data)
        if reference_action is None:
            return False
        return {"reference_action": reference_action}


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _resolve_reference_workspace(
    *,
    workspace_id: int,
    user_id: int,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> Workspace:
    global_owner = _is_global_owner(user_id)
    workspace = await workspace_service.set_active_workspace(
        workspace_id=workspace_id,
        user_id=user_id,
        global_owner=global_owner,
    )
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=user_id,
        minimum_role="viewer",
        global_owner=global_owner,
    )
    if workspace.is_system:
        raise WorkspaceAccessError(
            "Системный Velvet использует основной интерфейс Стэл, а не личный модуль."
        )
    if not await workspace_product_service.is_module_enabled(
        workspace_id=workspace.id,
        module_key="references",
    ):
        raise WorkspaceAccessError("Модуль выключен или не разрешён Стэл.")
    return workspace


async def handle_workspace_reference_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace = await _resolve_reference_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    dashboard = await build_workspace_reference_dashboard(database, workspace)
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            dashboard.text,
            reply_markup=dashboard.keyboard,
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            await callback.message.answer(
                dashboard.text,
                reply_markup=dashboard.keyboard,
            )
    await callback.answer()


async def handle_workspace_reference_action(
    callback: CallbackQuery,
    reference_action: WorkspaceReferenceAction,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace = await _resolve_reference_workspace(
            workspace_id=reference_action.workspace_id,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    if reference_action.action == "help":
        await callback.answer(
            "Добавление: /refadd Имя персонажа. Затем отправляйте фото или "
            "изображения-документы и завершите /refdone.",
            show_alert=True,
        )
        return
    if reference_action.action != "open":
        await callback.answer("Неизвестное действие.", show_alert=True)
        return

    character = await load_character_by_id(
        database,
        character_id=reference_action.character_id,
        workspace_id=workspace.id,
    )
    if character is None:
        await callback.answer(
            "Персонаж не найден в этом пространстве.",
            show_alert=True,
        )
        return
    references = await list_character_references(
        database,
        character.id,
        limit=50,
        workspace_id=workspace.id,
    )
    if not references:
        await callback.answer(
            f"У {character.name} пока нет референсов. Добавление: /refadd {character.name}",
            show_alert=True,
        )
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Не удалось определить чат.", show_alert=True)
        return
    try:
        await send_reference_collection(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            character=character,
            references=references,
        )
    except TelegramAPIError:
        await callback.answer(
            "Telegram не смог открыть один из референсов.",
            show_alert=True,
        )
        return
    await callback.answer()


def register_workspace_reference_dashboard(router: Router) -> None:
    router.callback_query.register(
        handle_workspace_reference_entry,
        WorkspaceCallback.filter(
            (F.action == "module") & (F.module_key == "references")
        ),
    )
    router.callback_query.register(
        handle_workspace_reference_action,
        WorkspaceReferenceActionFilter(),
    )


__all__ = (
    "WorkspaceReferenceActionFilter",
    "handle_workspace_reference_action",
    "handle_workspace_reference_entry",
    "register_workspace_reference_dashboard",
)
