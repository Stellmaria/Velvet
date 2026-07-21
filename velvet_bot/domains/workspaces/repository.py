from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import (
    Workspace,
    WorkspaceChannel,
    WorkspaceChannelKind,
    WorkspaceDownloadsMode,
    WorkspaceMembership,
    WorkspaceRole,
    WorkspaceSettings,
)


class WorkspaceRepository:
    """PostgreSQL boundary for isolated archive workspaces and memberships."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def create(
        self,
        *,
        name: str,
        slug: str,
        owner_user_id: int,
    ) -> Workspace:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    INSERT INTO workspaces (slug, name, is_system)
                    VALUES ($1::VARCHAR, $2::VARCHAR, FALSE)
                    RETURNING id, slug, name, is_system, created_at, updated_at
                    """,
                    slug,
                    name,
                )
                if row is None:
                    raise RuntimeError("Не удалось создать пространство.")
                workspace_id = int(row["id"])
                await connection.execute(
                    """
                    INSERT INTO workspace_members (workspace_id, user_id, role)
                    VALUES ($1::BIGINT, $2::BIGINT, 'owner')
                    """,
                    workspace_id,
                    int(owner_user_id),
                )
                await connection.execute(
                    """
                    INSERT INTO workspace_settings (workspace_id)
                    VALUES ($1::BIGINT)
                    ON CONFLICT (workspace_id) DO NOTHING
                    """,
                    workspace_id,
                )
                await connection.execute(
                    """
                    INSERT INTO user_workspace_preferences (user_id, active_workspace_id)
                    VALUES ($1::BIGINT, $2::BIGINT)
                    ON CONFLICT (user_id) DO UPDATE
                    SET active_workspace_id = EXCLUDED.active_workspace_id,
                        updated_at = NOW()
                    """,
                    int(owner_user_id),
                    workspace_id,
                )
        return self._row_to_workspace(row)

    async def get(self, workspace_id: int) -> Workspace | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT id, slug, name, is_system, created_at, updated_at
                FROM workspaces
                WHERE id = $1::BIGINT
                """,
                int(workspace_id),
            )
        return self._row_to_workspace(row) if row is not None else None

    async def get_by_slug(self, slug: str) -> Workspace | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT id, slug, name, is_system, created_at, updated_at
                FROM workspaces
                WHERE slug = $1::VARCHAR
                """,
                slug,
            )
        return self._row_to_workspace(row) if row is not None else None

    async def list_for_user(self, user_id: int) -> tuple[Workspace, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT w.id, w.slug, w.name, w.is_system, w.created_at, w.updated_at
                FROM workspaces AS w
                JOIN workspace_members AS wm ON wm.workspace_id = w.id
                WHERE wm.user_id = $1::BIGINT
                ORDER BY w.is_system DESC, w.name ASC, w.id ASC
                """,
                int(user_id),
            )
        return tuple(self._row_to_workspace(row) for row in rows)

    async def get_membership(
        self,
        *,
        workspace_id: int,
        user_id: int,
    ) -> WorkspaceMembership | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT workspace_id, user_id, role, created_at, updated_at
                FROM workspace_members
                WHERE workspace_id = $1::BIGINT
                  AND user_id = $2::BIGINT
                """,
                int(workspace_id),
                int(user_id),
            )
        return self._row_to_membership(row) if row is not None else None

    async def upsert_member(
        self,
        *,
        workspace_id: int,
        user_id: int,
        role: WorkspaceRole,
    ) -> WorkspaceMembership:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspace_members (workspace_id, user_id, role)
                VALUES ($1::BIGINT, $2::BIGINT, $3::VARCHAR)
                ON CONFLICT (workspace_id, user_id) DO UPDATE
                SET role = EXCLUDED.role,
                    updated_at = NOW()
                RETURNING workspace_id, user_id, role, created_at, updated_at
                """,
                int(workspace_id),
                int(user_id),
                role,
            )
        if row is None:
            raise RuntimeError("Не удалось сохранить участника пространства.")
        return self._row_to_membership(row)

    async def remove_member(self, *, workspace_id: int, user_id: int) -> bool:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                result = await connection.execute(
                    """
                    DELETE FROM workspace_members
                    WHERE workspace_id = $1::BIGINT
                      AND user_id = $2::BIGINT
                    """,
                    int(workspace_id),
                    int(user_id),
                )
                await connection.execute(
                    """
                    DELETE FROM user_workspace_preferences
                    WHERE user_id = $1::BIGINT
                      AND active_workspace_id = $2::BIGINT
                    """,
                    int(user_id),
                    int(workspace_id),
                )
        return result != "DELETE 0"

    async def get_active_workspace_id(self, user_id: int) -> int | None:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT active_workspace_id
                FROM user_workspace_preferences
                WHERE user_id = $1::BIGINT
                """,
                int(user_id),
            )
        return int(value) if value is not None else None

    async def set_active_workspace_id(
        self,
        *,
        user_id: int,
        workspace_id: int,
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO user_workspace_preferences (user_id, active_workspace_id)
                VALUES ($1::BIGINT, $2::BIGINT)
                ON CONFLICT (user_id) DO UPDATE
                SET active_workspace_id = EXCLUDED.active_workspace_id,
                    updated_at = NOW()
                """,
                int(user_id),
                int(workspace_id),
            )

    async def get_settings(self, workspace_id: int) -> WorkspaceSettings | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    workspace_id,
                    timezone,
                    public_archive_enabled,
                    downloads_mode,
                    qwen_enabled,
                    created_at,
                    updated_at
                FROM workspace_settings
                WHERE workspace_id = $1::BIGINT
                """,
                int(workspace_id),
            )
        return self._row_to_settings(row) if row is not None else None

    async def update_settings(
        self,
        *,
        workspace_id: int,
        timezone: str,
        public_archive_enabled: bool,
        downloads_mode: WorkspaceDownloadsMode,
        qwen_enabled: bool,
    ) -> WorkspaceSettings:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                INSERT INTO workspace_settings (
                    workspace_id,
                    timezone,
                    public_archive_enabled,
                    downloads_mode,
                    qwen_enabled
                )
                VALUES ($1::BIGINT, $2::VARCHAR, $3::BOOLEAN, $4::VARCHAR, $5::BOOLEAN)
                ON CONFLICT (workspace_id) DO UPDATE
                SET timezone = EXCLUDED.timezone,
                    public_archive_enabled = EXCLUDED.public_archive_enabled,
                    downloads_mode = EXCLUDED.downloads_mode,
                    qwen_enabled = EXCLUDED.qwen_enabled,
                    updated_at = NOW()
                RETURNING
                    workspace_id,
                    timezone,
                    public_archive_enabled,
                    downloads_mode,
                    qwen_enabled,
                    created_at,
                    updated_at
                """,
                int(workspace_id),
                timezone,
                bool(public_archive_enabled),
                downloads_mode,
                bool(qwen_enabled),
            )
        if row is None:
            raise RuntimeError("Не удалось сохранить настройки пространства.")
        return self._row_to_settings(row)

    async def upsert_channel(
        self,
        *,
        workspace_id: int,
        kind: WorkspaceChannelKind,
        chat_id: int,
        url: str | None,
    ) -> WorkspaceChannel:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock($1::BIGINT)",
                    int(chat_id),
                )
                conflict_workspace_id = await connection.fetchval(
                    """
                    SELECT workspace_id
                    FROM workspace_channels
                    WHERE chat_id = $1::BIGINT
                      AND workspace_id <> $2::BIGINT
                    LIMIT 1
                    """,
                    int(chat_id),
                    int(workspace_id),
                )
                if conflict_workspace_id is not None:
                    raise ValueError(
                        "Этот Telegram-чат уже подключён к другому пространству."
                    )
                row = await connection.fetchrow(
                    """
                    INSERT INTO workspace_channels (workspace_id, kind, chat_id, url)
                    VALUES ($1::BIGINT, $2::VARCHAR, $3::BIGINT, $4::TEXT)
                    ON CONFLICT (workspace_id, kind) DO UPDATE
                    SET chat_id = EXCLUDED.chat_id,
                        url = EXCLUDED.url,
                        updated_at = NOW()
                    RETURNING workspace_id, kind, chat_id, url, created_at, updated_at
                    """,
                    int(workspace_id),
                    kind,
                    int(chat_id),
                    url,
                )
        if row is None:
            raise RuntimeError("Не удалось сохранить канал пространства.")
        return self._row_to_channel(row)

    async def list_channels(self, workspace_id: int) -> tuple[WorkspaceChannel, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT workspace_id, kind, chat_id, url, created_at, updated_at
                FROM workspace_channels
                WHERE workspace_id = $1::BIGINT
                ORDER BY kind ASC
                """,
                int(workspace_id),
            )
        return tuple(self._row_to_channel(row) for row in rows)

    @staticmethod
    def _row_to_workspace(row) -> Workspace:
        return Workspace(
            id=int(row["id"]),
            slug=str(row["slug"]),
            name=str(row["name"]),
            is_system=bool(row["is_system"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_membership(row) -> WorkspaceMembership:
        return WorkspaceMembership(
            workspace_id=int(row["workspace_id"]),
            user_id=int(row["user_id"]),
            role=str(row["role"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_settings(row) -> WorkspaceSettings:
        return WorkspaceSettings(
            workspace_id=int(row["workspace_id"]),
            timezone=str(row["timezone"]),
            public_archive_enabled=bool(row["public_archive_enabled"]),
            downloads_mode=str(row["downloads_mode"]),
            qwen_enabled=bool(row["qwen_enabled"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _row_to_channel(row) -> WorkspaceChannel:
        return WorkspaceChannel(
            workspace_id=int(row["workspace_id"]),
            kind=str(row["kind"]),
            chat_id=int(row["chat_id"]),
            url=str(row["url"]) if row["url"] is not None else None,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


__all__ = ("WorkspaceRepository",)
