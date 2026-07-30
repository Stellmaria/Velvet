from __future__ import annotations

from typing import Any

from aiogram import F, Router
from aiogram.filters import or_f
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from velvet_bot.domains.auf_runtime import (
    AufRuntimeAccessError,
    AufRuntimeService,
)
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.routers.workspace_auf import (
    AufCallback,
    AufForm,
    handle_auf_prompt,
    handle_auf_reference_message,
    handle_auf_reference_text,
)

from velvet_bot.presentation.telegram.routers.workspace_auf_legacy import (
    LegacyMeowCallback,
    LegacyMeowVideoCallback,
    MeowForm,
    MeowRuntimeForm,
    MeowVideoForm,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_grs import (
    handle_auf_action,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_balance import (
    handle_auf_balance,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_grs_balance import (
    handle_auf_grs_balance,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_root import (
    handle_auf_root_entry,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_runtime import (
    AufRuntimeCallback,
    AufRuntimeForm,
    handle_auf_runtime_action,
    handle_auf_runtime_callback,
    handle_auf_runtime_limit_input,
)
from velvet_bot.presentation.telegram.routers.workspace_auf_video_simple import (
    AufVideoCallback,
    AufVideoForm,
    handle_auf_video_action,
    handle_auf_video_entry,
    handle_auf_video_prompt,
    handle_auf_video_reference_message,
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
setattr(AufVideoCallback, "__separator__", "|")
setattr(LegacyMeowVideoCallback, "__separator__", "|")

def _auf_callback_filter(rule=None):
    return or_f(
        AufCallback.filter(rule),
        LegacyMeowCallback.filter(rule),
    )


def _auf_video_callback_filter(rule=None):
    return or_f(
        AufVideoCallback.filter(rule),
        LegacyMeowVideoCallback.filter(rule),
    )


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


class _AufScopedAccessPolicy:
    """Permit one already-authorized Auf handler without widening global access."""

    moderator_user_ids = frozenset()

    @staticmethod
    def allows_user(user: Any | None) -> bool:
        return user is not None


async def _require_auf_callback(
    callback: CallbackQuery,
    *,
    workspace_id: int,
    service: AufRuntimeService,
) -> bool:
    try:
        await service.require_workspace_access(
            workspace_id=workspace_id,
            actor_user_id=callback.from_user.id,
        )
    except AufRuntimeAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return False
    return True


async def _require_auf_message(
    message: Message,
    state: FSMContext,
    *,
    workspace_key: str,
    service: AufRuntimeService,
) -> bool:
    data = await state.get_data()
    legacy_key = workspace_key.replace("auf", "meow", 1)
    workspace_id = int(data.get(workspace_key) or data.get(legacy_key) or 0)
    try:
        await service.require_workspace_access(
            workspace_id=workspace_id,
            actor_user_id=message.from_user.id if message.from_user else 0,
        )
    except AufRuntimeAccessError as error:
        await state.clear()
        await message.answer(str(error))
        return False
    return True


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


async def handle_scoped_auf_action(
    callback: CallbackQuery,
    callback_data: AufCallback | LegacyMeowCallback,
    state: FSMContext,
    access_policy,
    kie_settings,
    database,
    ai_usage_service,
    ai_task_queue_service,
    auf_runtime_service: AufRuntimeService,
) -> None:
    if callback_data.action in {"runtime", "visibility_toggle"}:
        await handle_auf_runtime_action(
            callback,
            callback_data,
            state,
            auf_runtime_service,
        )
        return
    if not await _require_auf_callback(
        callback,
        workspace_id=callback_data.workspace_id,
        service=auf_runtime_service,
    ):
        return
    await handle_auf_action(
        callback,
        callback_data,
        state,
        _AufScopedAccessPolicy(),
        kie_settings,
        database,
        ai_usage_service,
        ai_task_queue_service,
    )


async def handle_scoped_auf_video_entry(
    callback: CallbackQuery,
    callback_data: AufCallback | LegacyMeowCallback,
    state: FSMContext,
    access_policy,
    kie_settings,
    auf_runtime_service: AufRuntimeService,
) -> None:
    if not await _require_auf_callback(
        callback,
        workspace_id=callback_data.workspace_id,
        service=auf_runtime_service,
    ):
        return
    await handle_auf_video_entry(
        callback,
        callback_data,
        state,
        _AufScopedAccessPolicy(),
        kie_settings,
    )


async def handle_scoped_auf_video_action(
    callback: CallbackQuery,
    callback_data: AufVideoCallback | LegacyMeowVideoCallback,
    state: FSMContext,
    access_policy,
    kie_settings,
    database,
    ai_usage_service,
    ai_task_queue_service,
    auf_runtime_service: AufRuntimeService,
) -> None:
    if not await _require_auf_callback(
        callback,
        workspace_id=callback_data.workspace_id,
        service=auf_runtime_service,
    ):
        return
    await handle_auf_video_action(
        callback,
        callback_data,
        state,
        _AufScopedAccessPolicy(),
        kie_settings,
        database,
        ai_usage_service,
        ai_task_queue_service,
    )


async def handle_scoped_auf_prompt(
    message: Message,
    state: FSMContext,
    access_policy,
    kie_settings,
    auf_runtime_service: AufRuntimeService,
) -> None:
    if not await _require_auf_message(
        message,
        state,
        workspace_key="auf_workspace_id",
        service=auf_runtime_service,
    ):
        return
    await handle_auf_prompt(
        message,
        state,
        _AufScopedAccessPolicy(),
        kie_settings,
    )


async def handle_scoped_auf_reference_message(
    message: Message,
    state: FSMContext,
    access_policy,
    kie_settings,
    auf_runtime_service: AufRuntimeService,
) -> None:
    if not await _require_auf_message(
        message,
        state,
        workspace_key="auf_workspace_id",
        service=auf_runtime_service,
    ):
        return
    await handle_auf_reference_message(
        message,
        state,
        _AufScopedAccessPolicy(),
        kie_settings,
    )


async def handle_scoped_auf_reference_text(
    message: Message,
    state: FSMContext,
    access_policy,
    kie_settings,
    auf_runtime_service: AufRuntimeService,
) -> None:
    if not await _require_auf_message(
        message,
        state,
        workspace_key="auf_workspace_id",
        service=auf_runtime_service,
    ):
        return
    await handle_auf_reference_text(
        message,
        state,
        _AufScopedAccessPolicy(),
        kie_settings,
    )


async def handle_scoped_auf_video_reference_message(
    message: Message,
    state: FSMContext,
    access_policy,
    kie_settings,
    auf_runtime_service: AufRuntimeService,
) -> None:
    if not await _require_auf_message(
        message,
        state,
        workspace_key="auf_video_workspace_id",
        service=auf_runtime_service,
    ):
        return
    await handle_auf_video_reference_message(
        message,
        state,
        _AufScopedAccessPolicy(),
        kie_settings,
    )


async def handle_scoped_auf_video_prompt(
    message: Message,
    state: FSMContext,
    access_policy,
    kie_settings,
    auf_runtime_service: AufRuntimeService,
) -> None:
    if not await _require_auf_message(
        message,
        state,
        workspace_key="auf_video_workspace_id",
        service=auf_runtime_service,
    ):
        return
    await handle_auf_video_prompt(
        message,
        state,
        _AufScopedAccessPolicy(),
        kie_settings,
    )


def register_workspace_home(router: Router) -> None:
    """Register canonical home plus module-scoped photo and video Auf flows."""

    router.callback_query.register(
        handle_workspace_home,
        WorkspaceCallback.filter(F.action == "home"),
    )
    router.callback_query.register(
        handle_auf_root_entry,
        WorkspaceCallback.filter(F.action.in_({"auf", "meow"})),
    )
    router.callback_query.register(
        handle_auf_balance,
        _auf_callback_filter(F.action == "balance"),
    )
    router.callback_query.register(
        handle_auf_grs_balance,
        _auf_callback_filter(F.action == "grs_balance"),
    )
    router.callback_query.register(
        handle_scoped_auf_video_entry,
        _auf_callback_filter(F.action == "animate"),
    )
    router.callback_query.register(
        handle_auf_runtime_callback,
        AufRuntimeCallback.filter(),
    )
    router.callback_query.register(
        handle_scoped_auf_video_action,
        _auf_video_callback_filter(),
    )
    router.callback_query.register(
        handle_scoped_auf_action,
        _auf_callback_filter(),
    )
    router.message.register(
        handle_auf_runtime_limit_input,
        or_f(AufRuntimeForm.waiting_limit, MeowRuntimeForm.waiting_limit),
        F.text,
    )
    router.message.register(
        handle_scoped_auf_video_reference_message,
        or_f(AufVideoForm.waiting_reference, MeowVideoForm.waiting_reference),
        F.photo | F.document,
    )
    router.message.register(
        handle_scoped_auf_video_prompt,
        or_f(AufVideoForm.waiting_prompt, MeowVideoForm.waiting_prompt),
        F.text,
    )
    router.message.register(
        handle_scoped_auf_reference_message,
        or_f(AufForm.collecting_references, MeowForm.collecting_references),
        F.photo | F.document,
    )
    router.message.register(
        handle_scoped_auf_reference_text,
        or_f(AufForm.collecting_references, MeowForm.collecting_references),
        F.text,
    )
    router.message.register(
        handle_scoped_auf_prompt,
        or_f(AufForm.waiting_prompt, MeowForm.waiting_prompt),
        F.text,
    )


__all__ = (
    "handle_workspace_home",
    "register_workspace_home",
)
