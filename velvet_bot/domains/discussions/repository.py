from __future__ import annotations

import json

from velvet_bot.database import Database
from velvet_bot.domains.discussions.models import DiscussionOverview, ParticipantStat


class DiscussionRepository:
    """PostgreSQL boundary for discussion reports and reaction updates."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _decode_reaction_breakdown(value) -> dict[str, int]:
        if not value:
            return {}
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return {}
        if not isinstance(value, dict):
            return {}
        return {
            str(key): max(0, int(count))
            for key, count in value.items()
            if int(count) > 0
        }

    async def is_tracked(self, chat_id: int) -> bool:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT 1
                FROM tracked_channels
                WHERE chat_id = $1::BIGINT
                  AND source_kind = 'discussion'
                  AND enabled = TRUE
                """,
                int(chat_id),
            )
        return value is not None

    async def get_parent_channel_id(self, chat_id: int) -> int | None:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """
                SELECT parent_channel_id
                FROM tracked_channels
                WHERE chat_id = $1::BIGINT
                  AND source_kind = 'discussion'
                  AND enabled = TRUE
                """,
                int(chat_id),
            )
        return int(value) if value is not None else None

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
        async with self._database.acquire() as connection:
            updated = await connection.fetchval(
                """
                UPDATE channel_posts AS post
                SET reactions_total = $3::INTEGER,
                    reaction_breakdown = $4::JSONB,
                    updated_at = NOW()
                WHERE post.channel_id = $1::BIGINT
                  AND post.message_id = $2::BIGINT
                  AND EXISTS (
                      SELECT 1
                      FROM tracked_channels AS tracked
                      WHERE tracked.chat_id = $1::BIGINT
                        AND tracked.source_kind = 'discussion'
                        AND tracked.enabled = TRUE
                  )
                RETURNING 1
                """,
                int(discussion_chat_id),
                int(discussion_message_id),
                sum(normalized.values()),
                json.dumps(normalized, ensure_ascii=False),
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
        async with self._database.acquire() as connection:
            async with connection.transaction():
                tracked = await connection.fetchval(
                    """
                    SELECT 1
                    FROM tracked_channels
                    WHERE chat_id = $1::BIGINT
                      AND source_kind = 'discussion'
                      AND enabled = TRUE
                    """,
                    int(discussion_chat_id),
                )
                if tracked is None:
                    return False
                row = await connection.fetchrow(
                    """
                    SELECT reaction_breakdown
                    FROM channel_posts
                    WHERE channel_id = $1::BIGINT
                      AND message_id = $2::BIGINT
                    FOR UPDATE
                    """,
                    int(discussion_chat_id),
                    int(discussion_message_id),
                )
                if row is None:
                    return False
                current = self._decode_reaction_breakdown(
                    row["reaction_breakdown"]
                )
                for key, value in normalized_delta.items():
                    next_value = max(0, current.get(key, 0) + value)
                    if next_value:
                        current[key] = next_value
                    else:
                        current.pop(key, None)
                updated = await connection.fetchval(
                    """
                    UPDATE channel_posts
                    SET reactions_total = $3::INTEGER,
                        reaction_breakdown = $4::JSONB,
                        updated_at = NOW()
                    WHERE channel_id = $1::BIGINT
                      AND message_id = $2::BIGINT
                    RETURNING 1
                    """,
                    int(discussion_chat_id),
                    int(discussion_message_id),
                    sum(current.values()),
                    json.dumps(current, ensure_ascii=False),
                )
        return updated is not None

    async def get_overview(self, chat_id: int) -> DiscussionOverview:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_messages,
                    COUNT(DISTINCT publication_key) AS total_publications,
                    COUNT(DISTINCT sender_id)
                        FILTER (WHERE sender_id IS NOT NULL)
                        AS unique_participants,
                    COUNT(*) FILTER (WHERE reply_to_message_id IS NOT NULL)
                        AS reply_messages,
                    COUNT(*) FILTER (WHERE media_type <> 'text')
                        AS media_messages,
                    COUNT(*) FILTER (WHERE has_spoiler) AS spoiler_messages,
                    COUNT(*) FILTER (WHERE is_prompt) AS prompt_messages,
                    COALESCE(SUM(reactions_total), 0) AS total_reactions,
                    MIN(posted_at) AS first_message_at,
                    MAX(posted_at) AS last_message_at
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                """,
                int(chat_id),
            )
            hashtag_row = await connection.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_hashtag_uses,
                    COUNT(DISTINCT hashtag.normalized_hashtag) AS unique_hashtags
                FROM channel_post_hashtags AS hashtag
                JOIN channel_posts AS post ON post.id = hashtag.post_id
                WHERE post.channel_id = $1::BIGINT
                """,
                int(chat_id),
            )
        return DiscussionOverview(
            chat_id=int(chat_id),
            total_messages=int(row["total_messages"] or 0),
            total_publications=int(row["total_publications"] or 0),
            unique_participants=int(row["unique_participants"] or 0),
            reply_messages=int(row["reply_messages"] or 0),
            media_messages=int(row["media_messages"] or 0),
            spoiler_messages=int(row["spoiler_messages"] or 0),
            prompt_messages=int(row["prompt_messages"] or 0),
            total_hashtag_uses=int(hashtag_row["total_hashtag_uses"] or 0),
            unique_hashtags=int(hashtag_row["unique_hashtags"] or 0),
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
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                WITH message_stats AS (
                    SELECT
                        sender_id,
                        COALESCE(MAX(sender_name), 'Неизвестный участник')
                            AS sender_name,
                        COUNT(*) AS message_count,
                        COUNT(*) FILTER (WHERE reply_to_message_id IS NOT NULL)
                            AS reply_count,
                        COUNT(*) FILTER (WHERE media_type <> 'text')
                            AS media_count,
                        MAX(posted_at) AS last_message_at
                    FROM channel_posts
                    WHERE channel_id = $1::BIGINT
                      AND sender_id IS NOT NULL
                    GROUP BY sender_id
                ),
                hashtag_stats AS (
                    SELECT
                        post.sender_id,
                        COUNT(hashtag.normalized_hashtag) AS hashtag_count
                    FROM channel_posts AS post
                    JOIN channel_post_hashtags AS hashtag
                      ON hashtag.post_id = post.id
                    WHERE post.channel_id = $1::BIGINT
                      AND post.sender_id IS NOT NULL
                    GROUP BY post.sender_id
                )
                SELECT
                    message_stats.sender_id,
                    message_stats.sender_name,
                    message_stats.message_count,
                    message_stats.reply_count,
                    message_stats.media_count,
                    COALESCE(hashtag_stats.hashtag_count, 0) AS hashtag_count,
                    message_stats.last_message_at
                FROM message_stats
                LEFT JOIN hashtag_stats
                  ON hashtag_stats.sender_id = message_stats.sender_id
                ORDER BY message_stats.message_count DESC,
                         message_stats.last_message_at DESC
                LIMIT $2::INTEGER
                """,
                int(chat_id),
                safe_limit,
            )
        return [
            ParticipantStat(
                sender_id=str(row["sender_id"]),
                sender_name=str(row["sender_name"]),
                message_count=int(row["message_count"] or 0),
                reply_count=int(row["reply_count"] or 0),
                media_count=int(row["media_count"] or 0),
                hashtag_count=int(row["hashtag_count"] or 0),
                last_message_at=row["last_message_at"],
            )
            for row in rows
        ]


__all__ = ("DiscussionRepository",)
