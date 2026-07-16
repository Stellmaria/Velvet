from __future__ import annotations

from velvet_bot.database import Database


async def create_set_candidate_from_duplicate(
    database: Database,
    *,
    duplicate_candidate_id: int,
    decided_by: int,
) -> int:
    """Turn one reviewed non-duplicate pair into a selectable set proposal."""
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            row = await connection.fetchrow(
                """
                SELECT dc.first_media_id, dc.second_media_id, dc.similarity_score,
                       m1.media_set_id AS first_set_id,
                       m2.media_set_id AS second_set_id
                FROM media_duplicate_candidates AS dc
                JOIN media_files AS m1 ON m1.id = dc.first_media_id
                JOIN media_files AS m2 ON m2.id = dc.second_media_id
                WHERE dc.id = $1::BIGINT
                FOR UPDATE OF dc, m1, m2
                """,
                int(duplicate_candidate_id),
            )
            if row is None:
                raise ValueError("Пара больше не найдена.")
            if row["first_set_id"] is not None or row["second_set_id"] is not None:
                raise ValueError("Один из материалов уже входит в сет.")

            media_ids = tuple(
                sorted((int(row["first_media_id"]), int(row["second_media_id"])))
            )
            context = await connection.fetchrow(
                """
                SELECT
                    COALESCE(
                        ARRAY_AGG(DISTINCT c.name ORDER BY c.name)
                            FILTER (WHERE c.id IS NOT NULL),
                        ARRAY[]::VARCHAR[]
                    ) AS characters,
                    MAX(cm.prompt_post_url)
                        FILTER (WHERE cm.prompt_post_url IS NOT NULL)
                        AS prompt_post_url
                FROM character_media AS cm
                LEFT JOIN characters AS c ON c.id = cm.character_id
                WHERE cm.media_id = ANY($1::BIGINT[])
                """,
                list(media_ids),
            )
            characters = tuple(
                str(value) for value in (context["characters"] if context else ()) if value
            )
            prompt_post_url = context["prompt_post_url"] if context else None
            title = (
                ("Сет: " + ", ".join(characters[:4]))[:160]
                if characters
                else "Новый медиасет"
            )
            key = f"visual:{media_ids[0]}:{media_ids[1]}"
            score = max(65, int(row["similarity_score"]))
            candidate_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO media_set_candidates (
                        candidate_key, suggested_title, reason, score, prompt_post_url
                    )
                    VALUES ($1::TEXT, $2::VARCHAR, $3::TEXT, $4::SMALLINT, $5::TEXT)
                    ON CONFLICT (candidate_key) DO UPDATE
                    SET status = 'pending',
                        suggested_title = EXCLUDED.suggested_title,
                        reason = EXCLUDED.reason,
                        score = EXCLUDED.score,
                        prompt_post_url = COALESCE(
                            media_set_candidates.prompt_post_url,
                            EXCLUDED.prompt_post_url
                        ),
                        decided_by = NULL,
                        decided_at = NULL,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    key,
                    title,
                    "Сходная композиция или стиль, но материалы решено не считать дублями.",
                    score,
                    prompt_post_url,
                )
            )
            for media_id in media_ids:
                await connection.execute(
                    """
                    INSERT INTO media_set_candidate_items (
                        candidate_id, media_id, selected, context_score, reason
                    )
                    VALUES ($1::BIGINT, $2::BIGINT, TRUE, $3::SMALLINT, $4::TEXT)
                    ON CONFLICT (candidate_id, media_id) DO UPDATE
                    SET selected = TRUE,
                        context_score = EXCLUDED.context_score,
                        reason = EXCLUDED.reason
                    """,
                    candidate_id,
                    media_id,
                    score,
                    "Предложено из проверки похожей пары",
                )
            await connection.execute(
                """
                UPDATE media_duplicate_candidates
                SET status = 'ignored', decided_by = $2::BIGINT,
                    decided_at = NOW(), updated_at = NOW()
                WHERE id = $1::BIGINT
                """,
                int(duplicate_candidate_id),
                int(decided_by),
            )
    return candidate_id


def install_media_sets_compatibility() -> None:
    """Replace the first implementation before Telegram handlers import it."""
    import velvet_bot.media_sets as media_sets

    media_sets.create_set_candidate_from_duplicate = create_set_candidate_from_duplicate


install_media_sets_compatibility()

__all__ = (
    "create_set_candidate_from_duplicate",
    "install_media_sets_compatibility",
)
