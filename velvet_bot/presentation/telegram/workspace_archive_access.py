from __future__ import annotations

from aiogram.types import CallbackQuery

from velvet_bot.archive_catalog import get_archive_page
from velvet_bot.database import Database
from velvet_bot.domains.archive.models import ArchivePage
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    WorkspacePersonalArchiveAction,
)


def is_global_workspace_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def resolve_workspace_archive_access(
    *,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
    user_id: int,
    workspace_id: int,
) -> tuple[Workspace, bool]:
    """Resolve one personal archive and return whether the actor has owner access."""

    global_owner = is_global_workspace_owner(user_id)
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
    membership = await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=int(user_id),
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
    return workspace, membership.role == "owner" or global_owner


async def load_workspace_archive_action_page(
    callback: CallbackQuery,
    archive_action: WorkspacePersonalArchiveAction,
    database: Database,
    *,
    workspace: Workspace,
    validate_media_id: bool = True,
) -> ArchivePage | None:
    """Load the target archive page and emit stable user-facing errors."""

    page = await get_archive_page(
        database,
        archive_action.character_id,
        archive_action.offset,
        workspace_id=workspace.id,
        include_adult_restricted=True,
        include_oversized_images=True,
    )
    if page is None:
        await callback.answer(
            "Персонаж не найден в этом пространстве.",
            show_alert=True,
        )
        return None
    if page.media is None:
        await callback.answer("Архив персонажа пока пуст.", show_alert=True)
        return None
    if (
        validate_media_id
        and archive_action.media_id
        and archive_action.media_id != page.media.id
    ):
        await callback.answer(
            "Архив изменился. Откройте материал заново.",
            show_alert=True,
        )
        return None
    return page


__all__ = (
    "is_global_workspace_owner",
    "load_workspace_archive_action_page",
    "resolve_workspace_archive_access",
)
