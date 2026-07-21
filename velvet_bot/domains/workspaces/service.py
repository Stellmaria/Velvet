from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from velvet_bot.domains.workspaces.models import (
    DEFAULT_WORKSPACE_ID,
    WORKSPACE_CHANNEL_KINDS,
    WORKSPACE_DOWNLOAD_MODES,
    WORKSPACE_ROLES,
    Workspace,
    WorkspaceChannel,
    WorkspaceChannelKind,
    WorkspaceDownloadsMode,
    WorkspaceMembership,
    WorkspaceRole,
    WorkspaceSettings,
)
from velvet_bot.domains.workspaces.repository import WorkspaceRepository

_ROLE_PRIORITY: dict[WorkspaceRole, int] = {
    "viewer": 10,
    "reviewer": 20,
    "editor": 30,
    "admin": 40,
    "owner": 50,
}
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class WorkspaceAccessError(PermissionError):
    pass


def normalize_workspace_name(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise ValueError("Название пространства не может быть пустым.")
    if len(cleaned) > 128:
        raise ValueError("Название пространства не должно быть длиннее 128 символов.")
    return cleaned


def normalize_workspace_slug(value: str) -> str:
    cleaned = _SLUG_RE.sub("-", value.strip().casefold()).strip("-")
    if not cleaned:
        raise ValueError("Короткое имя пространства не может быть пустым.")
    if len(cleaned) > 64:
        raise ValueError("Короткое имя пространства не должно быть длиннее 64 символов.")
    return cleaned


def validate_workspace_url(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if not cleaned.startswith("https://t.me/"):
        raise ValueError("Ссылка пространства должна начинаться с https://t.me/.")
    if len(cleaned) > 512:
        raise ValueError("Ссылка пространства слишком длинная.")
    return cleaned


def validate_timezone(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("Часовой пояс не может быть пустым.")
    try:
        ZoneInfo(cleaned)
    except ZoneInfoNotFoundError as error:
        raise ValueError("Укажите корректный IANA-часовой пояс.") from error
    return cleaned


class WorkspaceService:
    """Application rules for tenant membership and per-workspace configuration."""

    def __init__(self, repository: WorkspaceRepository) -> None:
        self._repository = repository

    async def create_personal_workspace(
        self,
        *,
        name: str,
        slug: str,
        owner_user_id: int,
    ) -> Workspace:
        return await self._repository.create(
            name=normalize_workspace_name(name),
            slug=normalize_workspace_slug(slug),
            owner_user_id=int(owner_user_id),
        )

    async def list_for_user(
        self,
        *,
        user_id: int,
        global_owner: bool = False,
    ) -> tuple[Workspace, ...]:
        items = list(await self._repository.list_for_user(int(user_id)))
        if global_owner and all(item.id != DEFAULT_WORKSPACE_ID for item in items):
            system = await self._repository.get(DEFAULT_WORKSPACE_ID)
            if system is not None:
                items.insert(0, system)
        return tuple(items)

    async def require_role(
        self,
        *,
        workspace_id: int,
        user_id: int,
        minimum_role: WorkspaceRole = "viewer",
        global_owner: bool = False,
    ) -> WorkspaceMembership:
        if minimum_role not in WORKSPACE_ROLES:
            raise ValueError("Неизвестная роль пространства.")
        if global_owner:
            workspace = await self._repository.get(int(workspace_id))
            if workspace is None:
                raise WorkspaceAccessError("Пространство не найдено.")
            membership = await self._repository.get_membership(
                workspace_id=int(workspace_id),
                user_id=int(user_id),
            )
            if membership is not None:
                return membership
            now = workspace.updated_at
            return WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=int(user_id),
                role="owner",
                created_at=now,
                updated_at=now,
            )

        membership = await self._repository.get_membership(
            workspace_id=int(workspace_id),
            user_id=int(user_id),
        )
        if membership is None:
            raise WorkspaceAccessError("У вас нет доступа к этому пространству.")
        if _ROLE_PRIORITY[membership.role] < _ROLE_PRIORITY[minimum_role]:
            raise WorkspaceAccessError("Недостаточно прав в этом пространстве.")
        return membership

    async def set_member_role(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        member_user_id: int,
        role: WorkspaceRole,
        global_owner: bool = False,
    ) -> WorkspaceMembership:
        if role not in WORKSPACE_ROLES:
            raise ValueError("Неизвестная роль пространства.")
        await self.require_role(
            workspace_id=workspace_id,
            user_id=actor_user_id,
            minimum_role="admin",
            global_owner=global_owner,
        )
        if role == "owner" and not global_owner:
            actor = await self.require_role(
                workspace_id=workspace_id,
                user_id=actor_user_id,
                minimum_role="owner",
            )
            if actor.role != "owner":
                raise WorkspaceAccessError("Только владелец может назначить владельца.")
        return await self._repository.upsert_member(
            workspace_id=int(workspace_id),
            user_id=int(member_user_id),
            role=role,
        )

    async def configure_channel(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        kind: WorkspaceChannelKind,
        chat_id: int,
        url: str | None,
        global_owner: bool = False,
    ) -> WorkspaceChannel:
        if kind not in WORKSPACE_CHANNEL_KINDS:
            raise ValueError("Неизвестное назначение канала.")
        await self.require_role(
            workspace_id=workspace_id,
            user_id=actor_user_id,
            minimum_role="admin",
            global_owner=global_owner,
        )
        return await self._repository.upsert_channel(
            workspace_id=int(workspace_id),
            kind=kind,
            chat_id=int(chat_id),
            url=validate_workspace_url(url),
        )

    async def update_settings(
        self,
        *,
        workspace_id: int,
        actor_user_id: int,
        timezone: str,
        public_archive_enabled: bool,
        downloads_mode: WorkspaceDownloadsMode,
        qwen_enabled: bool,
        global_owner: bool = False,
    ) -> WorkspaceSettings:
        if downloads_mode not in WORKSPACE_DOWNLOAD_MODES:
            raise ValueError("Неизвестный режим скачивания.")
        await self.require_role(
            workspace_id=workspace_id,
            user_id=actor_user_id,
            minimum_role="admin",
            global_owner=global_owner,
        )
        return await self._repository.update_settings(
            workspace_id=int(workspace_id),
            timezone=validate_timezone(timezone),
            public_archive_enabled=bool(public_archive_enabled),
            downloads_mode=downloads_mode,
            qwen_enabled=bool(qwen_enabled),
        )


__all__ = (
    "WorkspaceAccessError",
    "WorkspaceService",
    "normalize_workspace_name",
    "normalize_workspace_slug",
    "validate_timezone",
    "validate_workspace_url",
)
