from __future__ import annotations

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.workspace_archive_dashboard import (
    build_workspace_archive_dashboard,
)
from velvet_bot.presentation.telegram.workspace_archive_delivery_controller import (
    register_workspace_archive_delivery,
)
from velvet_bot.presentation.telegram.workspace_archive_mutation_controller import (
    register_workspace_archive_mutations,
)
from velvet_bot.presentation.telegram.workspace_archive_navigation_controller import (
    register_workspace_archive_navigation,
)
from velvet_bot.presentation.telegram.workspace_archive_social_controller import (
    register_workspace_archive_social_actions,
)
from velvet_bot.presentation.telegram.workspace_media_policy_controller import (
    register_workspace_media_policy,
)
from velvet_bot.workspace_ui import WorkspaceCallback


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _resolve_archive_workspace(
    *,
    callback_data: WorkspaceCallback,
    user_id: int,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> Workspace:
    global_owner = _is_global_owner(user_id)
    workspace = await workspace_service.set_active_workspace(
        workspace_id=callback_data.workspace_id,
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
        module_key="archive",
    ):
        raise WorkspaceAccessError("Модуль выключен или не разрешён Стэл.")
    return workspace


async def handle_workspace_archive_dashboard(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace = await _resolve_archive_workspace(
            callback_data=callback_data,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    dashboard = await build_workspace_archive_dashboard(database, workspace)
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


def register_workspace_archive_dashboard(router: Router) -> None:
    """Register canonical archive flows before broad child routers."""

    router.callback_query.register(
        handle_workspace_archive_dashboard,
        WorkspaceCallback.filter(
            (F.action == "module") & (F.module_key == "archive")
        ),
    )
    register_workspace_archive_navigation(router)
    register_workspace_media_policy(router)
    register_workspace_archive_social_actions(router)
    register_workspace_archive_mutations(router)
    register_workspace_archive_delivery(router)


__all__ = (
    "handle_workspace_archive_dashboard",
    "register_workspace_archive_dashboard",
)
