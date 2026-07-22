from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Database


class WorkspaceDeletionError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class DeletedWorkspace:
    id: int
    name: str


class WorkspaceDeletionService:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def describe_owned_workspace(
        self,
        *,
        workspace_id: int,
        user_id: int,
    ) -> DeletedWorkspace:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT w.id, w.name, w.is_system, wm.role
                FROM workspaces AS w
                JOIN workspace_members AS wm
                  ON wm.workspace_id = w.id
                 AND wm.user_id = $2::BIGINT
                WHERE w.id = $1::BIGINT
                """,
                int(workspace_id),
                int(user_id),
            )
        if row is None:
            raise WorkspaceDeletionError("Пространство не найдено или вам не принадлежит.")
        if bool(row["is_system"]):
            raise WorkspaceDeletionError("Системное пространство Velvet удалить нельзя.")
        if str(row["role"]) != "owner":
            raise WorkspaceDeletionError("Удалить пространство может только его владелец.")
        return DeletedWorkspace(id=int(row["id"]), name=str(row["name"]))

    async def delete_owned_workspace(
        self,
        *,
        workspace_id: int,
        user_id: int,
    ) -> DeletedWorkspace:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT w.id, w.name, w.is_system, wm.role
                    FROM workspaces AS w
                    JOIN workspace_members AS wm
                      ON wm.workspace_id = w.id
                     AND wm.user_id = $2::BIGINT
                    WHERE w.id = $1::BIGINT
                    FOR UPDATE OF w
                    """,
                    int(workspace_id),
                    int(user_id),
                )
                if row is None:
                    raise WorkspaceDeletionError(
                        "Пространство не найдено или уже удалено."
                    )
                if bool(row["is_system"]):
                    raise WorkspaceDeletionError("Системное пространство Velvet удалить нельзя.")
                if str(row["role"]) != "owner":
                    raise WorkspaceDeletionError(
                        "Удалить пространство может только его владелец."
                    )
                result = await connection.execute(
                    "DELETE FROM workspaces WHERE id = $1::BIGINT AND is_system = FALSE",
                    int(workspace_id),
                )
                if result == "DELETE 0":
                    raise WorkspaceDeletionError("Пространство уже удалено.")
        return DeletedWorkspace(id=int(row["id"]), name=str(row["name"]))


__all__ = (
    "DeletedWorkspace",
    "WorkspaceDeletionError",
    "WorkspaceDeletionService",
)
