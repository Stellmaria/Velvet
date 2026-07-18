from __future__ import annotations

from velvet_bot.database import Database


class MediaSetActionsRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def set_prompt_post_url(
        self,
        *,
        media_set_id: int,
        prompt_post_url: str,
    ) -> bool:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                updated = await connection.fetchval(
                    """
                    UPDATE media_sets
                    SET prompt_post_url = $2::TEXT, updated_at = NOW()
                    WHERE id = $1::BIGINT
                    RETURNING id
                    """,
                    int(media_set_id),
                    prompt_post_url,
                )
                if updated is None:
                    return False
                await connection.execute(
                    """
                    UPDATE character_media AS cm
                    SET prompt_post_url = $2::TEXT
                    FROM media_files AS mf
                    WHERE mf.media_set_id = $1::BIGINT
                      AND cm.media_id = mf.id
                      AND cm.prompt_post_url IS DISTINCT FROM $2::TEXT
                    """,
                    int(media_set_id),
                    prompt_post_url,
                )
        return True


__all__ = ("MediaSetActionsRepository",)
