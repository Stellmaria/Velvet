from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.media_sets import CreatedMediaSet


async def create_media_set(
    database: Database,
    *,
    candidate_id: int,
    created_by: int,
) -> CreatedMediaSet:
    """Create a set whose prompt is stored once in ``media_sets``."""
    async with database._require_pool().acquire() as connection:
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
                JOIN media_files AS mf ON mf.id = item.media_id
                WHERE item.candidate_id = $1::BIGINT
                  AND item.selected = TRUE
                  AND mf.media_set_id IS NULL
                ORDER BY item.media_id
                FOR UPDATE OF mf
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
            update_result = await connection.execute(
                """
                UPDATE media_files
                SET media_set_id = $1::BIGINT
                WHERE id = ANY($2::BIGINT[])
                  AND media_set_id IS NULL
                """,
                set_id,
                list(media_ids),
            )
            updated_count = int(update_result.rsplit(" ", 1)[-1])
            if updated_count != len(media_ids):
                raise ValueError(
                    "Часть выбранных материалов уже была добавлена в другой сет."
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

    return CreatedMediaSet(
        id=set_id,
        title=str(candidate["suggested_title"]),
        media_ids=media_ids,
        prompt_post_url=candidate["prompt_post_url"],
    )


def install_media_set_actions() -> None:
    import velvet_bot.media_sets as media_sets

    media_sets.create_media_set = create_media_set


__all__ = ("create_media_set", "install_media_set_actions")
