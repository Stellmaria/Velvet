from __future__ import annotations

from velvet_bot.domains.workspaces.models import WorkspaceMembership, WorkspaceRole
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.team_repository import WorkspaceTeamRepository

_ADMIN_ASSIGNABLE: frozenset[WorkspaceRole] = frozenset(
    {"editor", "reviewer", "viewer"}
)


class WorkspaceTeamService:
    """Authorization rules for workspace membership management."""

    def __init__(
        self,
        *,
        repository: WorkspaceTeamRepository,
        workspaces: WorkspaceService,
    ) -> None:
        self._repository = repository
        self._workspaces = workspaces

    async def list_members(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        global_owner: bool = False,
    ) -> tuple[WorkspaceMembership, ...]:
        await self._require_actor(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            global_owner=global_owner,
        )
        return await self._repository.list_members(workspace_id)

    async def add_member(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        user_id: int,
        role: WorkspaceRole,
        global_owner: bool = False,
    ) -> WorkspaceMembership:
        actor = await self._require_actor(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            global_owner=global_owner,
        )
        self._validate_target_id(user_id)
        if int(user_id) == int(actor_user_id):
            raise WorkspaceAccessError("Нельзя добавить себя повторно через управление командой.")
        self._require_assignable(actor.role, role, global_owner=global_owner)
        return await self._repository.add_member(
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
        )

    async def change_role(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        user_id: int,
        role: WorkspaceRole,
        global_owner: bool = False,
    ) -> WorkspaceMembership:
        actor = await self._require_actor(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            global_owner=global_owner,
        )
        if int(user_id) == int(actor_user_id):
            raise WorkspaceAccessError("Свою роль нельзя менять через это меню.")
        target = await self._require_target(workspace_id=workspace_id, user_id=user_id)
        self._require_manageable(actor.role, target.role, global_owner=global_owner)
        self._require_assignable(actor.role, role, global_owner=global_owner)
        if target.role == role:
            return target
        return await self._repository.change_role(
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
        )

    async def remove_member(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        user_id: int,
        global_owner: bool = False,
    ) -> bool:
        actor = await self._require_actor(
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            global_owner=global_owner,
        )
        if int(user_id) == int(actor_user_id):
            raise WorkspaceAccessError("Нельзя удалить себя через управление командой.")
        target = await self._require_target(workspace_id=workspace_id, user_id=user_id)
        self._require_manageable(actor.role, target.role, global_owner=global_owner)
        return await self._repository.remove_member(
            workspace_id=workspace_id,
            user_id=user_id,
        )

    async def _require_actor(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        global_owner: bool,
    ) -> WorkspaceMembership:
        return await self._workspaces.require_role(
            workspace_id=int(workspace_id),
            user_id=int(actor_user_id),
            minimum_role="admin",
            global_owner=global_owner,
        )

    async def _require_target(
        self,
        *,
        workspace_id: int,
        user_id: int,
    ) -> WorkspaceMembership:
        target = await self._repository.get_member(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if target is None:
            raise ValueError("Участник не найден в этом пространстве.")
        return target

    @staticmethod
    def _validate_target_id(user_id: int) -> None:
        if int(user_id) <= 0:
            raise ValueError("Telegram ID должен быть положительным числом.")

    @staticmethod
    def _require_manageable(
        actor_role: WorkspaceRole,
        target_role: WorkspaceRole,
        *,
        global_owner: bool,
    ) -> None:
        if global_owner or actor_role == "owner":
            return
        if actor_role != "admin" or target_role in {"owner", "admin"}:
            raise WorkspaceAccessError(
                "Администратор может управлять только редакторами, проверяющими и зрителями."
            )

    @staticmethod
    def _require_assignable(
        actor_role: WorkspaceRole,
        role: WorkspaceRole,
        *,
        global_owner: bool,
    ) -> None:
        if global_owner or actor_role == "owner":
            return
        if actor_role != "admin" or role not in _ADMIN_ASSIGNABLE:
            raise WorkspaceAccessError(
                "Администратор не может назначать владельца или администратора."
            )


__all__ = ("WorkspaceTeamService",)
