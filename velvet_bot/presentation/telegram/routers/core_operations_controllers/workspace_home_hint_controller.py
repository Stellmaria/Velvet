from __future__ import annotations

from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.workspace_command_menu import (
    set_workspace_chat_commands,
)
from velvet_bot.presentation.telegram.workspace_home_presentation import (
    build_workspace_home_presentation,
)
from velvet_bot.workspace_ui import WorkspaceCallback

router = Router(name=__name__)


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


@router.callback_query(WorkspaceCallback.filter(F.action == "helptoggle"))
async def handle_workspace_help_toggle(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    user_id = callback.from_user.id
    global_owner = _is_global_owner(user_id)
    try:
        workspace = await workspace_service.set_active_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=user_id,
            global_owner=global_owner,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    await callback.answer()
    if workspace.is_system:
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "Системная панель использует отдельные настройки."
            )
        return
    try:
        await workspace_service.require_role(
            workspace_id=workspace.id,
            user_id=user_id,
            minimum_role="owner",
            global_owner=global_owner,
        )
    except WorkspaceAccessError as error:
        if isinstance(callback.message, Message):
            await callback.message.answer(f"❌ {escape(str(error))}")
        return

    try:
        await workspace_product_service.toggle_button_hints(workspace.id)
        presentation = await build_workspace_home_presentation(
            workspace=workspace,
            user_id=user_id,
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            global_owner=global_owner,
        )
    except ValueError as error:
        if isinstance(callback.message, Message):
            await callback.message.answer(str(error))
        return

    if not isinstance(callback.message, Message):
        return
    try:
        await callback.message.edit_text(
            presentation.text,
            reply_markup=presentation.keyboard,
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await set_workspace_chat_commands(
        callback.bot,
        callback.message.chat.id,
        presentation.role,
    )


__all__ = ("router",)
