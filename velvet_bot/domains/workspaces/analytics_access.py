from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID, WorkspaceRole
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService

_ANALYTICS_CHANNEL_KINDS = ("analytics", "publication", "public")
_CHANNEL_PRIORITY = {"analytics": 0, "publication": 1, "public": 2}


@dataclass(frozen=True, slots=True)
class AnalyticsWorkspaceContext:
    workspace_id: int
    channel_ids: tuple[int, ...]
    primary_channel_id: int | None
    discussion_chat_ids: tuple[int, ...]
    is_system: bool
    error: str | None = None

    @property
    def allowed(self) -> bool:
        return self.error is None and self.primary_channel_id is not None


async def resolve_analytics_workspace_context(
    database: Database,
    workspace_service: WorkspaceService,
    *,
    user_id: int,
    minimum_role: WorkspaceRole,
    system_channel_ids: frozenset[int],
) -> AnalyticsWorkspaceContext:
    global_owner = int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID
    try:
        workspace = await workspace_service.resolve_active_workspace(
            user_id=int(user_id),
            global_owner=global_owner,
        )
    except WorkspaceAccessError as error:
        return AnalyticsWorkspaceContext(
            workspace_id=DEFAULT_WORKSPACE_ID,
            channel_ids=tuple(sorted(system_channel_ids)),
            primary_channel_id=(min(system_channel_ids) if system_channel_ids else None),
            discussion_chat_ids=(),
            is_system=True,
            error=str(error),
        )

    if workspace.id == DEFAULT_WORKSPACE_ID:
        ordered = tuple(sorted(system_channel_ids))
        return AnalyticsWorkspaceContext(
            workspace_id=workspace.id,
            channel_ids=ordered,
            primary_channel_id=(ordered[0] if ordered else None),
            discussion_chat_ids=(),
            is_system=True,
            error=(None if ordered else "Каналы для аналитики не настроены."),
        )

    try:
        await workspace_service.require_role(
            workspace_id=workspace.id,
            user_id=int(user_id),
            minimum_role=minimum_role,
            global_owner=global_owner,
        )
    except WorkspaceAccessError as error:
        return AnalyticsWorkspaceContext(
            workspace_id=workspace.id,
            channel_ids=(),
            primary_channel_id=None,
            discussion_chat_ids=(),
            is_system=False,
            error=str(error),
        )

    async with database.acquire() as connection:
        module_enabled = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = 'analytics'
            """,
            int(workspace.id),
        )
        rows = await connection.fetch(
            """
            SELECT kind, chat_id
            FROM workspace_channels
            WHERE workspace_id = $1::BIGINT
              AND kind = ANY($2::VARCHAR[])
            """,
            int(workspace.id),
            list(_ANALYTICS_CHANNEL_KINDS),
        )
        discussion_rows = await connection.fetch(
            """
            SELECT chat_id
            FROM workspace_channels
            WHERE workspace_id = $1::BIGINT
              AND kind = 'discussion'
            ORDER BY chat_id
            """,
            int(workspace.id),
        )

    ordered_rows = sorted(
        rows,
        key=lambda row: (_CHANNEL_PRIORITY.get(str(row["kind"]), 99), int(row["chat_id"])),
    )
    channel_ids = tuple(dict.fromkeys(int(row["chat_id"]) for row in ordered_rows))
    discussion_ids = tuple(int(row["chat_id"]) for row in discussion_rows)
    if not module_enabled:
        error = "Модуль аналитики выключен или не разрешён Стэл."
    elif not channel_ids:
        error = "Для пространства не подключён канал аналитики или публикаций."
    else:
        error = None
    return AnalyticsWorkspaceContext(
        workspace_id=workspace.id,
        channel_ids=channel_ids,
        primary_channel_id=(channel_ids[0] if channel_ids else None),
        discussion_chat_ids=discussion_ids,
        is_system=False,
        error=error,
    )


async def resolve_analytics_ingest_workspace(
    database: Database,
    *,
    chat_id: int,
    system_channel_ids: frozenset[int],
) -> int | None:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT DISTINCT wc.workspace_id
            FROM workspace_channels AS wc
            JOIN workspace_modules AS module
              ON module.workspace_id = wc.workspace_id
             AND module.module_key = 'analytics'
             AND module.is_allowed
             AND module.is_enabled
            WHERE wc.chat_id = $1::BIGINT
              AND wc.kind = ANY($2::VARCHAR[])
            ORDER BY wc.workspace_id
            """,
            int(chat_id),
            list(_ANALYTICS_CHANNEL_KINDS),
        )
    if len(rows) > 1:
        raise RuntimeError("Telegram-чат привязан к нескольким пространствам.")
    if rows:
        return int(rows[0]["workspace_id"])
    if int(chat_id) in system_channel_ids:
        return DEFAULT_WORKSPACE_ID
    return None


async def workspace_owns_discussion_chat(
    database: Database,
    *,
    workspace_id: int,
    chat_id: int,
) -> bool:
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT TRUE
            FROM workspace_channels
            WHERE workspace_id = $1::BIGINT
              AND kind = 'discussion'
              AND chat_id = $2::BIGINT
            """,
            int(workspace_id),
            int(chat_id),
        )
    return bool(value)


__all__ = (
    "AnalyticsWorkspaceContext",
    "resolve_analytics_ingest_workspace",
    "resolve_analytics_workspace_context",
    "workspace_owns_discussion_chat",
)
