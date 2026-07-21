from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import DEFAULT_WORKSPACE_ID, WorkspaceRole
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService


@dataclass(frozen=True, slots=True)
class ReferenceWorkspaceAccess:
    workspace_id: int
    error: str | None = None

    @property
    def allowed(self) -> bool:
        return self.error is None


async def _module_enabled(
    database: Database,
    *,
    workspace_id: int,
    module_key: str,
) -> bool:
    if int(workspace_id) == DEFAULT_WORKSPACE_ID:
        return True
    async with database.acquire() as connection:
        value = await connection.fetchval(
            """
            SELECT is_allowed AND is_enabled
            FROM workspace_modules
            WHERE workspace_id = $1::BIGINT
              AND module_key = $2::VARCHAR
            """,
            int(workspace_id),
            module_key,
        )
    return bool(value)


async def require_reference_workspace_access(
    database: Database,
    workspace_service: WorkspaceService,
    *,
    workspace_id: int,
    user_id: int,
    minimum_role: WorkspaceRole,
    require_qwen: bool = False,
) -> None:
    if int(workspace_id) == DEFAULT_WORKSPACE_ID:
        return
    global_owner = int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID
    await workspace_service.require_role(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        minimum_role=minimum_role,
        global_owner=global_owner,
    )
    if not await _module_enabled(
        database,
        workspace_id=workspace_id,
        module_key="references",
    ):
        raise WorkspaceAccessError("Модуль референсов выключен или не разрешён Стэл.")
    if not require_qwen:
        return
    if not await _module_enabled(
        database,
        workspace_id=workspace_id,
        module_key="qwen",
    ):
        raise WorkspaceAccessError("Модуль Qwen выключен или не разрешён Стэл.")
    async with database.acquire() as connection:
        qwen_enabled = await connection.fetchval(
            """
            SELECT qwen_enabled
            FROM workspace_settings
            WHERE workspace_id = $1::BIGINT
            """,
            int(workspace_id),
        )
    if qwen_enabled is False:
        raise WorkspaceAccessError("Qwen выключен в настройках пространства.")


async def resolve_personal_reference_access(
    database: Database,
    workspace_service: WorkspaceService,
    *,
    user_id: int,
    minimum_role: WorkspaceRole,
    require_qwen: bool = False,
) -> ReferenceWorkspaceAccess | None:
    global_owner = int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID
    try:
        workspace = await workspace_service.resolve_active_workspace(
            user_id=int(user_id),
            global_owner=global_owner,
        )
    except WorkspaceAccessError:
        return None
    if workspace.id == DEFAULT_WORKSPACE_ID:
        return None
    try:
        await require_reference_workspace_access(
            database,
            workspace_service,
            workspace_id=workspace.id,
            user_id=user_id,
            minimum_role=minimum_role,
            require_qwen=require_qwen,
        )
    except WorkspaceAccessError as error:
        return ReferenceWorkspaceAccess(workspace_id=workspace.id, error=str(error))
    return ReferenceWorkspaceAccess(workspace_id=workspace.id)


__all__ = (
    "ReferenceWorkspaceAccess",
    "require_reference_workspace_access",
    "resolve_personal_reference_access",
)
