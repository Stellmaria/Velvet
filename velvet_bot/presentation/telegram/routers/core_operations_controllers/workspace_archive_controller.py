from __future__ import annotations

from typing import Any

from aiogram import Router
from aiogram.filters import BaseFilter
from aiogram.types import Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_command_filtering import (
    command_name,
)
from velvet_bot.presentation.telegram.workspace_archive_dashboard import (
    build_workspace_archive_dashboard,
)
from velvet_bot.presentation.telegram.workspace_command_menu import (
    set_workspace_chat_commands,
)

router = Router(name=__name__)


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


class PersonalArchiveCommandFilter(BaseFilter):
    async def __call__(
        self,
        message: Message,
        workspace_service: WorkspaceService,
        workspace_product_service: WorkspaceProductService,
    ) -> dict[str, Any] | bool:
        if command_name(message) != "archive":
            return False
        user = message.from_user or message.guest_bot_caller_user
        if user is None:
            return False
        try:
            workspace = await workspace_service.resolve_active_workspace(
                user_id=user.id,
                global_owner=_is_global_owner(user.id),
            )
            if workspace.is_system:
                return False
            membership = await workspace_service.require_role(
                workspace_id=workspace.id,
                user_id=user.id,
                minimum_role="viewer",
                global_owner=_is_global_owner(user.id),
            )
            enabled = await workspace_product_service.is_module_enabled(
                workspace_id=workspace.id,
                module_key="archive",
            )
        except (WorkspaceAccessError, ValueError):
            return False
        if not enabled:
            return False
        return {
            "personal_workspace": workspace,
            "workspace_role": membership.role,
        }


@router.message(PersonalArchiveCommandFilter())
async def handle_personal_archive_command(
    message: Message,
    database: Database,
    personal_workspace: Workspace,
    workspace_role: str,
) -> None:
    dashboard = await build_workspace_archive_dashboard(
        database,
        personal_workspace,
        command_context=True,
    )
    await message.answer(
        dashboard.text,
        reply_markup=dashboard.keyboard,
    )
    await set_workspace_chat_commands(message.bot, message.chat.id, workspace_role)


__all__ = ("PersonalArchiveCommandFilter", "router")
