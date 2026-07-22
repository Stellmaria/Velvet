from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.product_models import (
    DEFAULT_PERSONAL_MODULE_KEYS,
    GLOBAL_WORKSPACE_CREATOR_ID,
    WORKSPACE_MODULE_KEYS,
    WorkspaceModuleKey,
    WorkspaceModuleSetting,
)
from velvet_bot.domains.workspaces.product_repository import WorkspaceProductRepository
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.repository import WorkspaceRepository


@dataclass(frozen=True, slots=True)
class WorkspaceGrantAdminSummary:
    user_id: int
    allowed_modules: tuple[WorkspaceModuleKey, ...]
    max_workspaces: int
    is_active: bool
    owned_workspace_count: int
    granted_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class WorkspaceAdminSummary:
    workspace_id: int
    name: str
    slug: str
    owner_user_id: int
    public_archive_enabled: bool
    character_count: int
    created_at: datetime
    updated_at: datetime


class WorkspaceAdministrationAccessError(PermissionError):
    pass


class WorkspaceAdministrationService:
    """Global-owner administration of personal workspace grants and module policy."""

    def __init__(self, database: Database) -> None:
        self._database = database
        self._product_repository = WorkspaceProductRepository(database)
        self._workspace_repository = WorkspaceRepository(database)
        self._product_service = WorkspaceProductService(
            product_repository=self._product_repository,
            workspace_repository=self._workspace_repository,
        )

    @staticmethod
    def _require_stel(actor_user_id: int) -> None:
        if int(actor_user_id) != GLOBAL_WORKSPACE_CREATOR_ID:
            raise WorkspaceAdministrationAccessError(
                "Управление личными пространствами доступно только Стэл."
            )

    @staticmethod
    def _module_tuple(values: Any) -> tuple[WorkspaceModuleKey, ...]:
        raw = {str(item) for item in (values or ())}
        return tuple(item for item in WORKSPACE_MODULE_KEYS if item in raw)

    @classmethod
    def _grant_from_row(cls, row: Any) -> WorkspaceGrantAdminSummary:
        return WorkspaceGrantAdminSummary(
            user_id=int(row["user_id"]),
            allowed_modules=cls._module_tuple(row["allowed_modules"]),
            max_workspaces=int(row["max_workspaces"]),
            is_active=bool(row["is_active"]),
            owned_workspace_count=int(row["owned_workspace_count"] or 0),
            granted_at=row["granted_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _workspace_from_row(row: Any) -> WorkspaceAdminSummary:
        return WorkspaceAdminSummary(
            workspace_id=int(row["workspace_id"]),
            name=str(row["name"]),
            slug=str(row["slug"]),
            owner_user_id=int(row["owner_user_id"]),
            public_archive_enabled=bool(row["public_archive_enabled"]),
            character_count=int(row["character_count"] or 0),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def count_creation_grants(self, *, actor_user_id: int) -> int:
        self._require_stel(actor_user_id)
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                "SELECT COUNT(*) FROM workspace_creation_grants"
            )
        return int(value or 0)

    async def list_creation_grants(
        self,
        *,
        actor_user_id: int,
        limit: int = 8,
        offset: int = 0,
    ) -> tuple[WorkspaceGrantAdminSummary, ...]:
        self._require_stel(actor_user_id)
        safe_limit = max(1, min(int(limit), 50))
        safe_offset = max(0, int(offset))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    grant.user_id,
                    grant.allowed_modules,
                    grant.max_workspaces,
                    grant.is_active,
                    grant.granted_at,
                    grant.updated_at,
                    (
                        SELECT COUNT(*)
                        FROM workspace_members AS member
                        JOIN workspaces AS workspace
                          ON workspace.id = member.workspace_id
                        WHERE member.user_id = grant.user_id
                          AND member.role = 'owner'
                          AND NOT workspace.is_system
                    ) AS owned_workspace_count
                FROM workspace_creation_grants AS grant
                ORDER BY grant.is_active DESC, grant.updated_at DESC, grant.user_id
                LIMIT $1::INTEGER OFFSET $2::INTEGER
                """,
                safe_limit,
                safe_offset,
            )
        return tuple(self._grant_from_row(row) for row in rows)

    async def get_creation_grant(
        self,
        *,
        actor_user_id: int,
        user_id: int,
    ) -> WorkspaceGrantAdminSummary | None:
        self._require_stel(actor_user_id)
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    grant.user_id,
                    grant.allowed_modules,
                    grant.max_workspaces,
                    grant.is_active,
                    grant.granted_at,
                    grant.updated_at,
                    (
                        SELECT COUNT(*)
                        FROM workspace_members AS member
                        JOIN workspaces AS workspace
                          ON workspace.id = member.workspace_id
                        WHERE member.user_id = grant.user_id
                          AND member.role = 'owner'
                          AND NOT workspace.is_system
                    ) AS owned_workspace_count
                FROM workspace_creation_grants AS grant
                WHERE grant.user_id = $1::BIGINT
                """,
                int(user_id),
            )
        return self._grant_from_row(row) if row is not None else None

    async def ensure_creation_grant(
        self,
        *,
        actor_user_id: int,
        user_id: int,
    ) -> WorkspaceGrantAdminSummary:
        self._require_stel(actor_user_id)
        if int(user_id) <= 0:
            raise ValueError("Telegram ID должен быть положительным числом.")
        current = await self.get_creation_grant(
            actor_user_id=actor_user_id,
            user_id=user_id,
        )
        if current is None:
            await self._product_service.grant_creation_access(
                actor_user_id=actor_user_id,
                user_id=user_id,
                allowed_modules=DEFAULT_PERSONAL_MODULE_KEYS,
            )
        elif not current.is_active:
            await self.set_creation_grant_active(
                actor_user_id=actor_user_id,
                user_id=user_id,
                is_active=True,
            )
        result = await self.get_creation_grant(
            actor_user_id=actor_user_id,
            user_id=user_id,
        )
        if result is None:
            raise RuntimeError("Не удалось сохранить разрешение пользователя.")
        return result

    async def set_creation_grant_active(
        self,
        *,
        actor_user_id: int,
        user_id: int,
        is_active: bool,
    ) -> WorkspaceGrantAdminSummary:
        self._require_stel(actor_user_id)
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                UPDATE workspace_creation_grants
                SET is_active = $2::BOOLEAN,
                    updated_at = NOW()
                WHERE user_id = $1::BIGINT
                """,
                int(user_id),
                bool(is_active),
            )
        if result == "UPDATE 0":
            raise ValueError("Разрешение для этого Telegram ID не найдено.")
        summary = await self.get_creation_grant(
            actor_user_id=actor_user_id,
            user_id=user_id,
        )
        if summary is None:
            raise RuntimeError("Разрешение исчезло после обновления.")
        return summary

    async def toggle_creation_grant_module(
        self,
        *,
        actor_user_id: int,
        user_id: int,
        module_key: WorkspaceModuleKey,
    ) -> WorkspaceGrantAdminSummary:
        self._require_stel(actor_user_id)
        if module_key not in WORKSPACE_MODULE_KEYS:
            raise ValueError("Неизвестный модуль.")
        current = await self.get_creation_grant(
            actor_user_id=actor_user_id,
            user_id=user_id,
        )
        if current is None:
            raise ValueError("Разрешение для этого Telegram ID не найдено.")
        selected = set(current.allowed_modules)
        if module_key in selected:
            selected.remove(module_key)
        else:
            selected.add(module_key)
        modules = tuple(item for item in WORKSPACE_MODULE_KEYS if item in selected)
        if not modules:
            raise ValueError("Нельзя убрать последний модуль будущего архива.")
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE workspace_creation_grants
                SET allowed_modules = $2::TEXT[],
                    updated_at = NOW()
                WHERE user_id = $1::BIGINT
                """,
                int(user_id),
                list(modules),
            )
        summary = await self.get_creation_grant(
            actor_user_id=actor_user_id,
            user_id=user_id,
        )
        if summary is None:
            raise RuntimeError("Разрешение исчезло после обновления модулей.")
        return summary

    async def count_personal_workspaces(self, *, actor_user_id: int) -> int:
        self._require_stel(actor_user_id)
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                "SELECT COUNT(*) FROM workspaces WHERE NOT is_system"
            )
        return int(value or 0)

    async def list_personal_workspaces(
        self,
        *,
        actor_user_id: int,
        limit: int = 8,
        offset: int = 0,
        owner_user_id: int | None = None,
    ) -> tuple[WorkspaceAdminSummary, ...]:
        self._require_stel(actor_user_id)
        safe_limit = max(1, min(int(limit), 50))
        safe_offset = max(0, int(offset))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    workspace.id AS workspace_id,
                    workspace.name,
                    workspace.slug,
                    owner.user_id AS owner_user_id,
                    COALESCE(settings.public_archive_enabled, FALSE)
                        AS public_archive_enabled,
                    COUNT(DISTINCT character.id) AS character_count,
                    workspace.created_at,
                    workspace.updated_at
                FROM workspaces AS workspace
                JOIN LATERAL (
                    SELECT member.user_id
                    FROM workspace_members AS member
                    WHERE member.workspace_id = workspace.id
                      AND member.role = 'owner'
                    ORDER BY member.created_at, member.user_id
                    LIMIT 1
                ) AS owner ON TRUE
                LEFT JOIN workspace_settings AS settings
                  ON settings.workspace_id = workspace.id
                LEFT JOIN characters AS character
                  ON character.workspace_id = workspace.id
                WHERE NOT workspace.is_system
                  AND ($3::BIGINT IS NULL OR owner.user_id = $3::BIGINT)
                GROUP BY
                    workspace.id,
                    workspace.name,
                    workspace.slug,
                    owner.user_id,
                    settings.public_archive_enabled,
                    workspace.created_at,
                    workspace.updated_at
                ORDER BY workspace.updated_at DESC, workspace.id DESC
                LIMIT $1::INTEGER OFFSET $2::INTEGER
                """,
                safe_limit,
                safe_offset,
                int(owner_user_id) if owner_user_id is not None else None,
            )
        return tuple(self._workspace_from_row(row) for row in rows)

    async def get_personal_workspace(
        self,
        *,
        actor_user_id: int,
        workspace_id: int,
    ) -> WorkspaceAdminSummary | None:
        self._require_stel(actor_user_id)
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    workspace.id AS workspace_id,
                    workspace.name,
                    workspace.slug,
                    owner.user_id AS owner_user_id,
                    COALESCE(settings.public_archive_enabled, FALSE)
                        AS public_archive_enabled,
                    COUNT(DISTINCT character.id) AS character_count,
                    workspace.created_at,
                    workspace.updated_at
                FROM workspaces AS workspace
                JOIN LATERAL (
                    SELECT member.user_id
                    FROM workspace_members AS member
                    WHERE member.workspace_id = workspace.id
                      AND member.role = 'owner'
                    ORDER BY member.created_at, member.user_id
                    LIMIT 1
                ) AS owner ON TRUE
                LEFT JOIN workspace_settings AS settings
                  ON settings.workspace_id = workspace.id
                LEFT JOIN characters AS character
                  ON character.workspace_id = workspace.id
                WHERE workspace.id = $1::BIGINT
                  AND NOT workspace.is_system
                GROUP BY
                    workspace.id,
                    workspace.name,
                    workspace.slug,
                    owner.user_id,
                    settings.public_archive_enabled,
                    workspace.created_at,
                    workspace.updated_at
                """,
                int(workspace_id),
            )
        return self._workspace_from_row(row) if row is not None else None

    async def list_workspace_modules(
        self,
        *,
        actor_user_id: int,
        workspace_id: int,
    ) -> tuple[WorkspaceModuleSetting, ...]:
        self._require_stel(actor_user_id)
        workspace = await self.get_personal_workspace(
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
        )
        if workspace is None:
            raise ValueError("Личное пространство не найдено.")
        return await self._product_repository.list_modules(int(workspace_id))

    async def toggle_workspace_module(
        self,
        *,
        actor_user_id: int,
        workspace_id: int,
        module_key: WorkspaceModuleKey,
    ) -> WorkspaceModuleSetting:
        self._require_stel(actor_user_id)
        if module_key not in WORKSPACE_MODULE_KEYS:
            raise ValueError("Неизвестный модуль.")
        workspace = await self.get_personal_workspace(
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
        )
        if workspace is None:
            raise ValueError("Личное пространство не найдено.")
        modules = await self._product_repository.list_modules(int(workspace_id))
        current = next(
            (item for item in modules if item.module_key == module_key),
            None,
        )
        new_allowed = not bool(current and current.is_allowed)
        setting = await self._product_service.set_module_allowed(
            actor_user_id=actor_user_id,
            workspace_id=workspace_id,
            module_key=cast(WorkspaceModuleKey, module_key),
            is_allowed=new_allowed,
        )
        if module_key == "public_archive" and not new_allowed:
            await self._product_service.set_public_archive_enabled(
                workspace_id=workspace_id,
                actor_user_id=actor_user_id,
                enabled=False,
                global_owner=True,
            )
        return setting


__all__ = (
    "WorkspaceAdminSummary",
    "WorkspaceAdministrationAccessError",
    "WorkspaceAdministrationService",
    "WorkspaceGrantAdminSummary",
)
