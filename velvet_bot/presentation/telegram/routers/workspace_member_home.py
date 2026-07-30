from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.workspace_ui import (
    WorkspaceCallback,
    build_member_workspace_select_keyboard,
    build_workspace_member_home_keyboard,
    format_workspace_member_home,
)

router = Router(name=__name__)


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _edit_or_answer(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup,
) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=reply_markup)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await callback.message.answer(text, reply_markup=reply_markup)


async def _notify(callback: CallbackQuery, text: str) -> None:
    if isinstance(callback.message, Message):
        await callback.message.answer(text)


async def _show_choices(
    callback: CallbackQuery,
    *,
    product_service: WorkspaceProductService,
) -> None:
    state = await product_service.get_start_state(callback.from_user.id)
    if not state.member_workspaces:
        await _notify(callback, "У вас больше нет командных пространств.")
        return
    await _edit_or_answer(
        callback,
        text=(
            "<b>👥 Пространства команды</b>\n\n"
            "Выберите пространство. После выбора оно станет активным только для "
            "вашего аккаунта; доступные действия определяет ваша роль."
        ),
        reply_markup=build_member_workspace_select_keyboard(state.member_workspaces),
    )


@router.callback_query(
    WorkspaceCallback.filter(F.action.in_({"memberhome", "memberselect"}))
)
async def handle_workspace_member_home(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    workspace_product_service: WorkspaceProductService,
    workspace_service: WorkspaceService,
) -> None:
    # Ack before database and rendering work so Telegram does not leave the button
    # spinning while a workspace dashboard is assembled.
    await callback.answer()

    if callback_data.action == "memberhome":
        await _show_choices(callback, product_service=workspace_product_service)
        return

    user_id = int(callback.from_user.id)
    try:
        workspace = await workspace_service.set_active_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
        if workspace.is_system:
            raise WorkspaceAccessError("Системное пространство не является командным архивом.")
        membership = await workspace_service.require_role(
            workspace_id=workspace.id,
            user_id=user_id,
            minimum_role="viewer",
            global_owner=_is_global_owner(user_id),
        )
        modules = await workspace_product_service.list_modules_for_member(
            workspace_id=workspace.id,
            actor_user_id=user_id,
            global_owner=_is_global_owner(user_id),
        )
    except WorkspaceAccessError as error:
        await _notify(callback, str(error))
        return

    enabled_modules = sum(
        item.is_allowed
        and item.is_enabled
        and membership.role
        in {
            "characters": {"owner", "admin", "editor"},
            "archive": {"owner", "admin", "editor", "reviewer", "viewer"},
            "references": {"owner", "admin", "editor", "reviewer", "viewer"},
            "watermark": {"owner", "admin"},
            "qwen": {"owner", "admin", "editor", "reviewer"},
            "publications": {"owner", "admin", "editor"},
            "analytics": {"owner", "admin", "editor", "reviewer"},
            "team": {"owner", "admin"},
        }.get(item.module_key, set())
        for item in modules
    )
    await _edit_or_answer(
        callback,
        text=format_workspace_member_home(
            workspace,
            role=membership.role,
            enabled_modules=enabled_modules,
        ),
        reply_markup=build_workspace_member_home_keyboard(
            workspace.id,
            role=membership.role,
            modules=modules,
        ),
    )


__all__ = ("router",)
