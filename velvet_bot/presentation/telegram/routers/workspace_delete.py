from __future__ import annotations

from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.deletion import (
    WorkspaceDeletionError,
    WorkspaceDeletionService,
)
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.workspace_ui import workspace_callback

router = Router(name=__name__)


class WorkspaceDeleteCallback(CallbackData, prefix="wsdel"):
    action: str
    workspace_id: int


def workspace_delete_callback(action: str, workspace_id: int) -> str:
    return WorkspaceDeleteCallback(action=action, workspace_id=int(workspace_id)).pack()


def _confirmation_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Да, удалить безвозвратно",
                    callback_data=workspace_delete_callback("confirm", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=workspace_delete_callback("cancel", workspace_id),
                )
            ],
        ]
    )


async def _show_confirmation(
    message: Message,
    *,
    workspace_id: int,
    user_id: int,
    database: Database,
) -> None:
    service = WorkspaceDeletionService(database)
    workspace = await service.describe_owned_workspace(
        workspace_id=workspace_id,
        user_id=user_id,
    )
    await message.answer(
        f"<b>Удалить «{escape(workspace.name)}»?</b>\n\n"
        "Будут безвозвратно удалены персонажи, материалы, референсы, настройки, "
        "публикации, привязки каналов и участники этого пространства. "
        "Действие нельзя отменить.",
        reply_markup=_confirmation_keyboard(workspace.id),
    )


@router.message(Command("workspace_delete"))
async def handle_workspace_delete_command(
    message: Message,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    parts = (message.text or "").split()
    explicit_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    try:
        if explicit_id is None:
            workspace = await workspace_service.resolve_active_workspace(
                user_id=user_id,
                global_owner=False,
            )
            workspace_id = workspace.id
        else:
            workspace_id = explicit_id
        await _show_confirmation(
            message,
            workspace_id=workspace_id,
            user_id=user_id,
            database=database,
        )
    except (WorkspaceAccessError, WorkspaceDeletionError) as error:
        await message.answer(str(error))


async def handle_workspace_delete_callback(
    callback: CallbackQuery,
    callback_data: WorkspaceDeleteCallback,
    state: FSMContext,
    database: Database,
) -> None:
    if callback_data.action == "cancel":
        await callback.answer("Удаление отменено.")
        if isinstance(callback.message, Message):
            await callback.message.edit_text("Удаление пространства отменено.")
        return
    if callback_data.action == "request":
        if not isinstance(callback.message, Message):
            await callback.answer("Откройте действие в личных сообщениях.", show_alert=True)
            return
        try:
            await _show_confirmation(
                callback.message,
                workspace_id=callback_data.workspace_id,
                user_id=callback.from_user.id,
                database=database,
            )
        except WorkspaceDeletionError as error:
            await callback.answer(str(error), show_alert=True)
            return
        await callback.answer()
        return
    if callback_data.action != "confirm":
        await callback.answer("Неизвестное действие.", show_alert=True)
        return
    try:
        deleted = await WorkspaceDeletionService(database).delete_owned_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
        )
    except WorkspaceDeletionError as error:
        await callback.answer(str(error), show_alert=True)
        return
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"<b>«{escape(deleted.name)}» удалено</b>\n\n"
            "Все данные личного пространства удалены. Если право на создание всё ещё "
            "активно, новый архив можно создать через /start.",
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="🌐 Публичные архивы",
                            callback_data=workspace_callback("publics"),
                        )
                    ]
                ]
            ),
        )
    await callback.answer("Пространство удалено.")


router.callback_query.register(
    handle_workspace_delete_callback,
    WorkspaceDeleteCallback.filter(),
)


__all__ = (
    "WorkspaceDeleteCallback",
    "router",
    "workspace_delete_callback",
)
