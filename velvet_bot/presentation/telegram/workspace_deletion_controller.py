from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.workspace_command_menu import (
    install_workspace_scoped_commands,
)
from velvet_bot.presentation.telegram.workspace_home_presentation import (
    build_workspace_home_presentation,
)
from velvet_bot.workspace_ui import WorkspaceCallback, build_start_keyboard, workspace_callback


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _resolve_owned_workspace(
    *,
    workspace_service: WorkspaceService,
    user_id: int,
    workspace_id: int = 0,
) -> Workspace:
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
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=int(user_id),
        minimum_role="owner",
        global_owner=global_owner,
    )
    return workspace


def build_workspace_delete_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить безвозвратно",
                    callback_data=workspace_callback(
                        "deleteconfirm",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=workspace_callback(
                        "deletecancel",
                        workspace_id=workspace_id,
                    ),
                )
            ],
        ]
    )


async def show_workspace_delete_confirmation(
    event: Message | CallbackQuery,
    *,
    workspace: Workspace,
) -> None:
    text = (
        f"<b>Удалить пространство «{escape(workspace.name)}»?</b>\n\n"
        "Будут удалены персонажи, материалы, референсы, категории, истории, "
        "назначения чатов, настройки и участники этого пространства.\n\n"
        "<b>Отменить это действие после подтверждения нельзя.</b>"
    )
    keyboard = build_workspace_delete_keyboard(workspace.id)
    if isinstance(event, CallbackQuery):
        if not isinstance(event.message, Message):
            await event.answer("Меню больше недоступно.", show_alert=True)
            return
        try:
            await event.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await event.message.answer(text, reply_markup=keyboard)
        await event.answer()
        return
    await event.answer(text, reply_markup=keyboard)


async def delete_workspace_data(
    database: Database,
    *,
    workspace_id: int,
) -> int:
    async with database.acquire() as connection:
        async with connection.transaction():
            workspace = await connection.fetchrow(
                """
                SELECT id, is_system
                FROM workspaces
                WHERE id = $1::BIGINT
                FOR UPDATE
                """,
                int(workspace_id),
            )
            if workspace is None:
                raise ValueError("Пространство уже удалено.")
            if bool(workspace["is_system"]):
                raise ValueError("Системное пространство удалить нельзя.")
            character_count = int(
                await connection.fetchval(
                    "SELECT COUNT(*) FROM characters WHERE workspace_id = $1::BIGINT",
                    int(workspace_id),
                )
                or 0
            )
            await connection.execute(
                "DELETE FROM characters WHERE workspace_id = $1::BIGINT",
                int(workspace_id),
            )
            result = await connection.execute(
                """
                DELETE FROM workspaces
                WHERE id = $1::BIGINT
                  AND NOT is_system
                """,
                int(workspace_id),
            )
            if result == "DELETE 0":
                raise ValueError("Пространство уже удалено.")
    return character_count


async def handle_workspace_delete_command(
    message: Message,
    workspace_service: WorkspaceService,
) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer(
            "Удаление пространства выполняется только в личных сообщениях."
        )
        return
    parts = (message.text or "").split()
    explicit_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    try:
        workspace = await _resolve_owned_workspace(
            workspace_service=workspace_service,
            user_id=message.from_user.id if message.from_user else 0,
            workspace_id=explicit_id,
        )
    except WorkspaceAccessError as error:
        await message.answer(str(error))
        return
    if workspace.is_system:
        await message.answer("Системное пространство Velvet удалить нельзя.")
        return
    await show_workspace_delete_confirmation(message, workspace=workspace)


async def handle_workspace_delete_prompt(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    workspace_service: WorkspaceService,
) -> None:
    try:
        workspace = await _resolve_owned_workspace(
            workspace_service=workspace_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    if workspace.is_system:
        await callback.answer(
            "Системное пространство удалить нельзя.",
            show_alert=True,
        )
        return
    await show_workspace_delete_confirmation(callback, workspace=workspace)


async def handle_workspace_delete_cancel(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    user_id = callback.from_user.id
    try:
        workspace = await _resolve_owned_workspace(
            workspace_service=workspace_service,
            user_id=user_id,
            workspace_id=callback_data.workspace_id,
        )
        presentation = await build_workspace_home_presentation(
            workspace=workspace,
            user_id=user_id,
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            global_owner=_is_global_owner(user_id),
        )
    except (WorkspaceAccessError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        await callback.message.edit_text(
            presentation.text,
            reply_markup=presentation.keyboard,
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            await callback.message.answer(
                presentation.text,
                reply_markup=presentation.keyboard,
            )
    await callback.answer()
    await install_workspace_scoped_commands(callback, role=presentation.role)


async def handle_workspace_delete_confirm(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace = await _resolve_owned_workspace(
            workspace_service=workspace_service,
            user_id=callback.from_user.id,
            workspace_id=callback_data.workspace_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    if workspace.is_system:
        await callback.answer(
            "Системное пространство удалить нельзя.",
            show_alert=True,
        )
        return

    try:
        deleted_characters = await delete_workspace_data(
            database,
            workspace_id=workspace.id,
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return

    await state.clear()
    start_state = await workspace_product_service.get_start_state(callback.from_user.id)
    personal_count = len(start_state.owned_workspaces) + len(start_state.member_workspaces)
    text = (
        f"<b>Пространство «{escape(workspace.name)}» удалено</b>\n\n"
        f"Удалено персонажей: <b>{deleted_characters}</b>.\n"
        "Разрешение Стэл не отозвано. Если лимит позволяет, новый архив можно создать снова."
    )
    keyboard = build_start_keyboard(
        can_create=start_state.can_create,
        has_workspace=bool(personal_count),
        workspace_count=personal_count,
        has_owned_workspace=bool(start_state.owned_workspaces),
    )
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest:
            await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer("Пространство удалено.")


def register_workspace_deletion(router: Router) -> None:
    router.message.register(
        handle_workspace_delete_command,
        Command("workspace_delete"),
    )
    router.callback_query.register(
        handle_workspace_delete_prompt,
        WorkspaceCallback.filter(F.action == "delete"),
    )
    router.callback_query.register(
        handle_workspace_delete_cancel,
        WorkspaceCallback.filter(F.action == "deletecancel"),
    )
    router.callback_query.register(
        handle_workspace_delete_confirm,
        WorkspaceCallback.filter(F.action == "deleteconfirm"),
    )


__all__ = (
    "build_workspace_delete_keyboard",
    "delete_workspace_data",
    "handle_workspace_delete_cancel",
    "handle_workspace_delete_command",
    "handle_workspace_delete_confirm",
    "handle_workspace_delete_prompt",
    "register_workspace_deletion",
    "show_workspace_delete_confirmation",
)
