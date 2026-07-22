from __future__ import annotations

from velvet_bot.database import Database


class WorkspaceMediaPreferenceRepository:
    """Private owner-only media marks that never affect public like counters."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def is_favorite(
        self,
        *,
        workspace_id: int,
        character_id: int,
        media_id: int,
        user_id: int,
    ) -> bool:
        async with self._database.acquire() as connection:
            return bool(
                await connection.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM workspace_media_owner_favorites
                        WHERE workspace_id = $1::BIGINT
                          AND character_id = $2::BIGINT
                          AND media_id = $3::BIGINT
                          AND user_id = $4::BIGINT
                    )
                    """,
                    int(workspace_id),
                    int(character_id),
                    int(media_id),
                    int(user_id),
                )
            )

    async def toggle_favorite(
        self,
        *,
        workspace_id: int,
        character_id: int,
        media_id: int,
        user_id: int,
    ) -> bool:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                belongs = await connection.fetchval(
                    """
                    SELECT 1
                    FROM character_media AS cm
                    JOIN characters AS c ON c.id = cm.character_id
                    WHERE cm.character_id = $2::BIGINT
                      AND cm.media_id = $3::BIGINT
                      AND c.workspace_id = $1::BIGINT
                    """,
                    int(workspace_id),
                    int(character_id),
                    int(media_id),
                )
                if belongs is None:
                    raise ValueError("Материал не принадлежит этому пространству.")
                deleted = await connection.fetchval(
                    """
                    DELETE FROM workspace_media_owner_favorites
                    WHERE workspace_id = $1::BIGINT
                      AND character_id = $2::BIGINT
                      AND media_id = $3::BIGINT
                      AND user_id = $4::BIGINT
                    RETURNING 1
                    """,
                    int(workspace_id),
                    int(character_id),
                    int(media_id),
                    int(user_id),
                )
                if deleted is not None:
                    return False
                inserted = await connection.fetchval(
                    """
                    INSERT INTO workspace_media_owner_favorites (
                        workspace_id,
                        character_id,
                        media_id,
                        user_id
                    )
                    VALUES ($1::BIGINT, $2::BIGINT, $3::BIGINT, $4::BIGINT)
                    ON CONFLICT DO NOTHING
                    RETURNING 1
                    """,
                    int(workspace_id),
                    int(character_id),
                    int(media_id),
                    int(user_id),
                )
                return inserted is not None


__all__ = ("WorkspaceMediaPreferenceRepository",)
