from __future__ import annotations

from dataclasses import dataclass

from velvet_bot.database import Database


@dataclass(frozen=True, slots=True)
class CreatedMediaSetRecord:
    id: int
    title: str
    media_ids: tuple[int, ...]
    prompt_post_url: str | None


class MediaSetActionsRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    def _acquire(self):
        return self._database.acquire()

    async def create_media_set(
        self,
        *,
        candidate_id: int,
        created_by: int,
    ) -> CreatedMediaSetRecord:
        async with self._acquire() as connection:
            async with connection.transaction():
                candidate = await connection.fetchrow(
                    """
                    SELECT id, suggested_title, prompt_post_url, status
                    FROM media_set_candidates
                    WHERE id = $1::BIGINT
                    FOR UPDATE
                    """,
                    int(candidate_id),
                )
                if candidate is None:
                    raise ValueError("Предложение сета больше не найдено.")
                if candidate["status"] != "pending":
                    raise ValueError("Это предложение уже обработано.")

                item_rows = await connection.fetch(
                    """
                    SELECT item.media_id
                    FROM media_set_candidate_items AS item
                    JOIN media_files AS media ON media.id = item.media_id
                    WHERE item.candidate_id = $1::BIGINT
                      AND item.selected = TRUE
                      AND media.media_set_id IS NULL
                    ORDER BY item.media_id
                    FOR UPDATE OF media
                    """,
                    int(candidate_id),
                )
                media_ids = tuple(int(row["media_id"]) for row in item_rows)
                if len(media_ids) < 2:
                    raise ValueError("Для сета нужно выбрать минимум два материала.")

                set_id = int(
                    await connection.fetchval(
                        """
                        INSERT INTO media_sets (title, prompt_post_url, created_by)
                        VALUES ($1::VARCHAR, $2::TEXT, $3::BIGINT)
                        RETURNING id
                        """,
                        str(candidate["suggested_title"])[:160],
                        candidate["prompt_post_url"],
                        int(created_by),
                    )
                )
                await connection.execute(
                    """
                    UPDATE media_files
                    SET media_set_id = $1::BIGINT
                    WHERE id = ANY($2::BIGINT[])
                      AND media_set_id IS NULL
                    """,
                    set_id,
                    list(media_ids),
                )
                if candidate["prompt_post_url"] is not None:
                    await connection.execute(
                        """
                        UPDATE character_media
                        SET prompt_post_url = $2::TEXT
                        WHERE media_id = ANY($1::BIGINT[])
                          AND prompt_post_url IS DISTINCT FROM $2::TEXT
                        """,
                        list(media_ids),
                        candidate["prompt_post_url"],
                    )
                await connection.execute(
                    """
                    UPDATE media_set_candidates
                    SET status = 'accepted',
                        decided_by = $2::BIGINT,
                        decided_at = NOW(),
                        created_set_id = $3::BIGINT,
                        updated_at = NOW()
                    WHERE id = $1::BIGINT
                    """,
                    int(candidate_id),
                    int(created_by),
                    set_id,
                )
                await connection.execute(
                    """
                    DELETE FROM media_set_candidate_items AS item
                    USING media_set_candidates AS other_candidate
                    WHERE item.candidate_id = other_candidate.id
                      AND other_candidate.status = 'pending'
                      AND other_candidate.id <> $1::BIGINT
                      AND item.media_id = ANY($2::BIGINT[])
                    """,
                    int(candidate_id),
                    list(media_ids),
                )
                await connection.execute(
                    """
                    UPDATE media_set_candidates AS other_candidate
                    SET status = 'ignored',
                        decided_by = COALESCE(other_candidate.decided_by, $2::BIGINT),
                        decided_at = COALESCE(other_candidate.decided_at, NOW()),
                        updated_at = NOW(),
                        reason = CASE
                            WHEN other_candidate.reason LIKE '%материалы уже вошли в подтверждённый сет.%'
                                THEN other_candidate.reason
                            ELSE other_candidate.reason || ' Скрыто: материалы уже вошли в подтверждённый сет.'
                        END
                    WHERE other_candidate.status = 'pending'
                      AND other_candidate.id <> $1::BIGINT
                      AND (
                            SELECT COUNT(*)
                            FROM media_set_candidate_items AS remaining
                            JOIN media_files AS media ON media.id = remaining.media_id
                            WHERE remaining.candidate_id = other_candidate.id
                              AND media.media_set_id IS NULL
                          ) < 2
                    """,
                    int(candidate_id),
                    int(created_by),
                )

        return CreatedMediaSetRecord(
            id=set_id,
            title=str(candidate["suggested_title"]),
            media_ids=media_ids,
            prompt_post_url=candidate["prompt_post_url"],
        )

    async def set_prompt_post_url(
        self,
        *,
        media_set_id: int,
        prompt_post_url: str,
    ) -> bool:
        async with self._acquire() as connection:
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


__all__ = (
    "CreatedMediaSetRecord",
    "MediaSetActionsRepository",
)
