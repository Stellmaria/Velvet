from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.routers.workspace_meow import MeowCallback
from velvet_bot.presentation.telegram.routers.workspace_meow_balance import (
    handle_meow_balance,
)
from velvet_bot.presentation.telegram.routers.workspace_meow_grs_balance import (
    handle_meow_grs_balance,
)
# Import the root adapter first: it replaces the legacy Create/Animate labels with
# Photo/Video before the photo flow captures the shared root keyboard function.
from velvet_bot.presentation.telegram.routers.workspace_meow_root import (
    handle_meow_root_entry,
)
from velvet_bot.presentation.telegram.routers.workspace_meow_photo import (
    MeowPhotoForm,
    handle_meow_photo_action,
    handle_meow_photo_command,
    handle_meow_photo_input,
)
from velvet_bot.presentation.telegram.routers.workspace_meow_photo_adjustments import (
    handle_photo_remove_last,
)
from velvet_bot.presentation.telegram.routers.workspace_meow_video_simple import (
    MeowVideoCallback,
    MeowVideoForm,
    handle_meow_video_action,
    handle_meow_video_entry,
    handle_meow_video_prompt,
    handle_meow_video_reference_message,
)
from velvet_bot.presentation.telegram.workspace_command_menu import (
    install_workspace_scoped_commands,
)
from velvet_bot.presentation.telegram.workspace_home_presentation import (
    build_workspace_home_presentation,
)
from velvet_bot.workspace_ui import WorkspaceCallback

# Aiogram uses ':' as its default CallbackData separator, while older callback
# values may contain the same symbol. Keep this callback family isolated.
setattr(MeowVideoCallback, "__separator__", "|")


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
    """Register canonical home plus owner-only photo and video Meow flows."""

    router.callback_query.register(
        handle_workspace_home,
        WorkspaceCallback.filter(F.action == "home"),
    )
    router.callback_query.register(
        handle_meow_root_entry,
        WorkspaceCallback.filter(F.action == "meow"),
    )
    router.callback_query.register(
        handle_meow_balance,
        MeowCallback.filter(F.action == "balance"),
    )
    router.callback_query.register(
        handle_meow_grs_balance,
        MeowCallback.filter(F.action == "grs_balance"),
    )
    router.callback_query.register(
        handle_meow_video_entry,
        MeowCallback.filter(F.action == "animate"),
    )
    router.callback_query.register(
        handle_meow_video_action,
        MeowVideoCallback.filter(),
    )
    router.callback_query.register(
        handle_photo_remove_last,
        MeowCallback.filter(F.action == "photo_remove_last"),
    )
    router.callback_query.register(
        handle_meow_photo_action,
        MeowCallback.filter(),
    )
    router.message.register(
        handle_meow_video_reference_message,
        MeowVideoForm.waiting_reference,
        F.photo | F.document,
    )
    router.message.register(
        handle_meow_video_prompt,
        MeowVideoForm.waiting_prompt,
        F.text,
    )
    for photo_state in (
        MeowPhotoForm.collecting_input,
        MeowPhotoForm.reviewing_input,
    ):
        router.message.register(
            handle_meow_photo_command,
            photo_state,
            Command("refs"),
        )
        router.message.register(
            handle_meow_photo_input,
            photo_state,
            F.photo | F.document | F.text,
        )


__all__ = (
    "handle_workspace_home",
    "register_workspace_home",
)
