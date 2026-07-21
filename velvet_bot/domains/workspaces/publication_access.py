from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID, WorkspaceRole
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService


@dataclass(frozen=True, slots=True)
class PublicationWorkspaceContext:
    workspace_id: int
    target_chat_id: int | None
    timezone: str
    is_system: bool
    error: str | None = None

    @property
    def allowed(self) -> bool:
        return self.error is None and self.target_chat_id is not None


async def resolve_publication_workspace_context(
    database: Database,
    workspace_service: WorkspaceService,
    *,
    user_id: int,
    minimum_role: WorkspaceRole,
    analytics_channel_ids: frozenset[int],
    system_timezone: str,
) -> PublicationWorkspaceContext:
    global_owner = int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID
    try:
        workspace = await workspace_service.resolve_active_workspace(
            user_id=int(user_id),
            global_owner=global_owner,
        )
    except WorkspaceAccessError as error:
        return PublicationWorkspaceContext(
            workspace_id=DEFAULT_WORKSPACE_ID,
            target_chat_id=None,
            timezone=system_timezone,
            is_system=True,
            error=str(error),
        )

    if workspace.id == DEFAULT_WORKSPACE_ID:
        target = sorted(analytics_channel_ids)[0] if analytics_channel_ids else None
        return PublicationWorkspaceContext(
            workspace_id=workspace.id,
            target_chat_id=target,
            timezone=system_timezone,
            is_system=True,
            error=(None if target is not None else "Основной канал публикаций не настроен."),
        )

    try:
        await workspace_service.require_role(
            workspace_id=workspace.id,
            user_id=int(user_id),
            minimum_role=minimum_role,
            global_owner=global_owner,
        )
    except WorkspaceAccessError as error:
        return PublicationWorkspaceContext(
            workspace_id=workspace.id,
            target_chat_id=None,
            timezone=system_timezone,
            is_system=False,
            error=str(error),
        )

    async with database.acquire() as connection:
        module_enabled = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = 'publications'
            """,
            int(workspace.id),
        )
        settings = await connection.fetchrow(
            """
            SELECT timezone
            FROM workspace_settings
            WHERE workspace_id = $1::BIGINT
            """,
            int(workspace.id),
        )
        target_chat_id = await connection.fetchval(
            """
            SELECT chat_id
            FROM workspace_channels
            WHERE workspace_id = $1::BIGINT
              AND kind = 'publication'
            """,
            int(workspace.id),
        )

    timezone_name = (
        str(settings["timezone"])
        if settings is not None and settings["timezone"]
        else system_timezone
    )
    if not module_enabled:
        error = "Модуль публикаций выключен или не разрешён Стэл."
    elif target_chat_id is None:
        error = "Для пространства не настроен канал публикаций."
    else:
        error = None
    return PublicationWorkspaceContext(
        workspace_id=workspace.id,
        target_chat_id=(int(target_chat_id) if target_chat_id is not None else None),
        timezone=timezone_name,
        is_system=False,
        error=error,
    )


__all__ = (
    "PublicationWorkspaceContext",
    "resolve_publication_workspace_context",
)
