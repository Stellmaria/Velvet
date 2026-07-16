from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.discussions.models import DiscussionOverview, ParticipantStat


class DiscussionRepository:
    """PostgreSQL boundary for discussion reports and reaction updates."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def is_tracked(self, chat_id: int) -> bool:
        async with self._database._require_pool().acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT 1
                FROM tracked_channels
                WHERE channel_id = $1::BIGINT
                  AND channel_type = 'discussion'
                """,
                int(chat_id),
            )
        return value is not None

    async def set_reaction_counts(
        self,
        *,
        discussion_chat_id: int,
        discussion_message_id: int,
        reaction_breakdown: dict[str, int],
    ) -> bool:
        normalized = {
            str(key): max(0, int(value))
            for key, value in reaction_breakdown.items()
            if int(value) > 0
        }
        async with self._database._require_pool().acquire() as connection:
            updated = await connection.fetchval(
                """
                UPDATE channel_posts
                SET reactions_json = $3::JSONB,
                    reactions_total = $4::INTEGER,
                    updated_at = NOW()
                WHERE channel_id = $1::BIGINT
                  AND message_id = $2::BIGINT
                  AND source_type = 'discussion'
                RETURNING 1
                """,
                int(discussion_chat_id),
                int(discussion_message_id),
                normalized,
                sum(normalized.values()),
            )
        return updated is not None

    async def apply_reaction_delta(
        self,
        *,
        discussion_chat_id: int,
        discussion_message_id: int,
        delta: dict[str, int],
    ) -> bool:
        normalized_delta = {
            str(key): int(value)
            for key, value in delta.items()
            if int(value) != 0
        }
        if not normalized_delta:
            return False
        async with self._database._require_pool().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT reactions_json
                    FROM channel_posts
                    WHERE channel_id = $1::BIGINT
                      AND message_id = $2::BIGINT
                      AND source_type = 'discussion'
                    FOR UPDATE
                    """,
                    int(discussion_chat_id),
                    int(discussion_message_id),
                )
                if row is None:
                    return False
                current = dict(row["reactions_json"] or {})
                for key, value in normalized_delta.items():
                    next_value = max(0, int(current.get(key, 0)) + value)
                    if next_value:
                        current[key] = next_value
                    else:
                        current.pop(key, None)
                updated = await connection.fetchval(
                    """
                    UPDATE channel_posts
                    SET reactions_json = $3::JSONB,
                        reactions_total = $4::INTEGER,
                        updated_at = NOW()
                    WHERE channel_id = $1::BIGINT
                      AND message_id = $2::BIGINT
                      AND source_type = 'discussion'
                    RETURNING 1
                    """,
                    int(discussion_chat_id),
                    int(discussion_message_id),
                    current,
                    sum(int(value) for value in current.values()),
                )
        return updated is not None

    async def get_overview(self, chat_id: int) -> DiscussionOverview | None:
        async with self._database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_messages,
                    COUNT(DISTINCT root_message_id)
                        FILTER (WHERE root_message_id IS NOT NULL)
                        AS total_publications,
                    COUNT(DISTINCT sender_id)
                        FILTER (WHERE sender_id IS NOT NULL)
                        AS unique_participants,
                    COUNT(*) FILTER (WHERE reply_to_message_id IS NOT NULL)
                        AS reply_messages,
                    COUNT(*) FILTER (WHERE media_type <> 'text')
                        AS media_messages,
                    COUNT(*) FILTER (WHERE has_spoiler) AS spoiler_messages,
                    COUNT(*) FILTER (WHERE is_prompt) AS prompt_messages,
                    COALESCE(SUM(hashtag_count), 0) AS total_hashtag_uses,
                    COUNT(DISTINCT hashtag_value) AS unique_hashtags,
                    COALESCE(SUM(reactions_total), 0) AS total_reactions,
                    MIN(posted_at) AS first_message_at,
                    MAX(posted_at) AS last_message_at
                FROM channel_posts AS cp
                LEFT JOIN LATERAL jsonb_array_elements_text(
                    COALESCE(cp.hashtags, '[]'::JSONB)
                ) AS hashtag(hashtag_value) ON TRUE
                WHERE cp.channel_id = $1::BIGINT
                  AND cp.source_type = 'discussion'
                """,
                int(chat_id),
            )
        if row is None or int(row["total_messages"] or 0) == 0:
            return None
        return DiscussionOverview(
            chat_id=int(chat_id),
            total_messages=int(row["total_messages"] or 0),
            total_publications=int(row["total_publications"] or 0),
            unique_participants=int(row["unique_participants"] or 0),
            reply_messages=int(row["reply_messages"] or 0),
            media_messages=int(row["media_messages"] or 0),
            spoiler_messages=int(row["spoiler_messages"] or 0),
            prompt_messages=int(row["prompt_messages"] or 0),
            total_hashtag_uses=int(row["total_hashtag_uses"] or 0),
            unique_hashtags=int(row["unique_hashtags"] or 0),
            total_reactions=int(row["total_reactions"] or 0),
            first_message_at=row["first_message_at"],
            last_message_at=row["last_message_at"],
        )

    async def list_participant_stats(
        self,
        chat_id: int,
        *,
        limit: int = 20,
    ) -> list[ParticipantStat]:
        safe_limit = max(1, min(int(limit), 100))
        async with self._database._require_pool().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    sender_id,
                    COALESCE(MAX(sender_name), 'Без имени') AS sender_name,
                    COUNT(*) AS message_count,
                    COUNT(*) FILTER (WHERE reply_to_message_id IS NOT NULL)
                        AS reply_count,
                    COUNT(*) FILTER (WHERE media_type <> 'text')
                        AS media_count,
                    COALESCE(SUM(hashtag_count), 0) AS hashtag_count,
                    MAX(posted_at) AS last_message_at
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                  AND source_type = 'discussion'
                  AND sender_id IS NOT NULL
                GROUP BY sender_id
                ORDER BY message_count DESC, last_message_at DESC
                LIMIT $2::INTEGER
                """,
                int(chat_id),
                safe_limit,
            )
        return [
            ParticipantStat(
                sender_id=str(row["sender_id"]),
                sender_name=str(row["sender_name"] or "Без имени"),
                message_count=int(row["message_count"] or 0),
                reply_count=int(row["reply_count"] or 0),
                media_count=int(row["media_count"] or 0),
                hashtag_count=int(row["hashtag_count"] or 0),
                last_message_at=row["last_message_at"],
            )
            for row in rows
        ]


__all__ = ("DiscussionRepository",)
