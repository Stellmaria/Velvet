from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.routers.workspace_meow import (
    MeowCallback,
    MeowForm,
    handle_meow_action,
    handle_meow_entry,
    handle_meow_prompt,
    handle_meow_reference_message,
    handle_meow_reference_text,
)
from velvet_bot.presentation.telegram.workspace_command_menu import (
    install_workspace_scoped_commands,
)
from velvet_bot.presentation.telegram.workspace_home_presentation import (
    build_workspace_home_presentation,
)
from velvet_bot.workspace_ui import WorkspaceCallback


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _resolve_workspace(
    *,
    callback_data: WorkspaceCallback,
    user_id: int,
    workspace_service: WorkspaceService,
) -> Workspace:
    global_owner = _is_global_owner(user_id)
    if callback_data.workspace_id:
        return await workspace_service.set_active_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=user_id,
            global_owner=global_owner,
        )
    return await workspace_service.resolve_active_workspace(
        user_id=user_id,
        global_owner=global_owner,
    )


async def handle_workspace_home(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    """Render the canonical role-aware workspace home screen."""

    await state.clear()
    user_id = callback.from_user.id
    try:
        workspace = await _resolve_workspace(
            callback_data=callback_data,
            user_id=user_id,
            workspace_service=workspace_service,
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


def register_workspace_home(router: Router) -> None:
    """Register canonical home and its owner-only Meow flow at bundle level."""

    router.callback_query.register(
        handle_workspace_home,
        WorkspaceCallback.filter(F.action == "home"),
    )
    router.callback_query.register(
        handle_meow_entry,
        WorkspaceCallback.filter(F.action == "meow"),
    )
    router.callback_query.register(
        handle_meow_action,
        MeowCallback.filter(),
    )
    router.message.register(
        handle_meow_reference_message,
        MeowForm.collecting_references,
        F.photo | F.document,
    )
    router.message.register(
        handle_meow_reference_text,
        MeowForm.collecting_references,
        F.text,
    )
    router.message.register(
        handle_meow_prompt,
        MeowForm.waiting_prompt,
        F.text,
    )


__all__ = (
    "handle_workspace_home",
    "register_workspace_home",
)
