from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import WorkspaceMembership, WorkspaceRole


class WorkspaceTeamRepository:
    """Transactional persistence boundary for one workspace team."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_members(self, workspace_id: int) -> tuple[WorkspaceMembership, ...]:
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT workspace_id, user_id, role, created_at, updated_at
                FROM workspace_members
                WHERE workspace_id = $1::BIGINT
                ORDER BY
                    CASE role
                        WHEN 'owner' THEN 1
                        WHEN 'admin' THEN 2
                        WHEN 'editor' THEN 3
                        WHEN 'reviewer' THEN 4
                        ELSE 5
                    END,
                    user_id
                """,
                int(workspace_id),
            )
        return tuple(self._map(row) for row in rows)

    async def get_member(
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
        return self._map(row) if row is not None else None

    async def add_member(
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
                ON CONFLICT (workspace_id, user_id) DO NOTHING
                RETURNING workspace_id, user_id, role, created_at, updated_at
                """,
                int(workspace_id),
                int(user_id),
                role,
            )
        if row is None:
            raise ValueError("Пользователь уже состоит в команде пространства.")
        return self._map(row)

    async def change_role(
        self,
        *,
        workspace_id: int,
        user_id: int,
        role: WorkspaceRole,
    ) -> WorkspaceMembership:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock($1::BIGINT)",
                    int(workspace_id),
                )
                row = await connection.fetchrow(
                    """
                    UPDATE workspace_members
                    SET role = $3::VARCHAR,
                        updated_at = NOW()
                    WHERE workspace_id = $1::BIGINT
                      AND user_id = $2::BIGINT
                    RETURNING workspace_id, user_id, role, created_at, updated_at
                    """,
                    int(workspace_id),
                    int(user_id),
                    role,
                )
        if row is None:
            raise ValueError("Участник не найден в этом пространстве.")
        return self._map(row)

    async def remove_member(self, *, workspace_id: int, user_id: int) -> bool:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock($1::BIGINT)",
                    int(workspace_id),
                )
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

    @staticmethod
    def _map(row) -> WorkspaceMembership:
        return WorkspaceMembership(
            workspace_id=int(row["workspace_id"]),
            user_id=int(row["user_id"]),
            role=str(row["role"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


__all__ = ("WorkspaceTeamRepository",)
