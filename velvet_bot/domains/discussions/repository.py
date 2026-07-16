from __future__ import annotations

import json

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
                FROM tracked_discussions
                WHERE discussion_chat_id = $1::BIGINT
                  AND is_active = TRUE
                """,
                int(chat_id),
            )
        return value is not None

    async def set_reaction_counts(
        self,
        *,
        discussion_chat_id: int,
        discussion_message_id: int,
        reaction_counts: dict[str, int],
    ) -> None:
        normalized = {
            str(key): max(0, int(value))
            for key, value in reaction_counts.items()
            if int(value) > 0
        }
        async with self._database._require_pool().acquire() as connection:
            await connection.execute(
                """
                UPDATE discussion_messages
                SET reaction_counts = $3::JSONB,
                    reaction_count = $4::INTEGER,
                    updated_at = NOW()
                WHERE discussion_chat_id = $1::BIGINT
                  AND discussion_message_id = $2::BIGINT
                """,
                int(discussion_chat_id),
                int(discussion_message_id),
                json.dumps(normalized, ensure_ascii=False),
                sum(normalized.values()),
            )

    async def apply_reaction_delta(
        self,
        *,
        discussion_chat_id: int,
        discussion_message_id: int,
        reaction_key: str,
        delta: int,
    ) -> None:
        async with self._database._require_pool().acquire() as connection:
            async with connection.transaction():
                row = await connection.fetchrow(
                    """
                    SELECT reaction_counts
                    FROM discussion_messages
                    WHERE discussion_chat_id = $1::BIGINT
                      AND discussion_message_id = $2::BIGINT
                    FOR UPDATE
                    """,
                    int(discussion_chat_id),
                    int(discussion_message_id),
                )
                if row is None:
                    return
                current = dict(row["reaction_counts"] or {})
                current_value = max(0, int(current.get(reaction_key, 0)) + int(delta))
                if current_value:
                    current[reaction_key] = current_value
                else:
                    current.pop(reaction_key, None)
                await connection.execute(
                    """
                    UPDATE discussion_messages
                    SET reaction_counts = $3::JSONB,
                        reaction_count = $4::INTEGER,
                        updated_at = NOW()
                    WHERE discussion_chat_id = $1::BIGINT
                      AND discussion_message_id = $2::BIGINT
                    """,
                    int(discussion_chat_id),
                    int(discussion_message_id),
                    json.dumps(current, ensure_ascii=False),
                    sum(int(value) for value in current.values()),
                )

    async def get_overview(
        self,
        discussion_chat_id: int,
    ) -> DiscussionOverview | None:
        async with self._database._require_pool().acquire() as connection:
            tracked = await connection.fetchrow(
                """
                SELECT discussion_chat_id, parent_channel_id,
                       chat_title, chat_username
                FROM tracked_discussions
                WHERE discussion_chat_id = $1::BIGINT
                """,
                int(discussion_chat_id),
            )
            if tracked is None:
                return None
            stats = await connection.fetchrow(
                """
                SELECT
                    COUNT(*) AS total_messages,
                    COUNT(*) FILTER (WHERE is_root) AS root_posts,
                    COUNT(*) FILTER (WHERE NOT is_root) AS replies,
                    COUNT(DISTINCT sender_user_id)
                        FILTER (WHERE sender_user_id IS NOT NULL) AS participant_count,
                    COALESCE(SUM(reaction_count), 0) AS reactions_total,
                    MIN(posted_at) AS first_message_at,
                    MAX(posted_at) AS last_message_at
                FROM discussion_messages
                WHERE discussion_chat_id = $1::BIGINT
                """,
                int(discussion_chat_id),
            )
        return DiscussionOverview(
            chat_id=int(tracked["discussion_chat_id"]),
            parent_channel_id=tracked["parent_channel_id"],
            chat_title=tracked["chat_title"],
            chat_username=tracked["chat_username"],
            total_messages=int(stats["total_messages"] or 0),
            root_posts=int(stats["root_posts"] or 0),
            replies=int(stats["replies"] or 0),
            participant_count=int(stats["participant_count"] or 0),
            reactions_total=int(stats["reactions_total"] or 0),
            first_message_at=stats["first_message_at"],
            last_message_at=stats["last_message_at"],
        )

    async def list_participant_stats(
        self,
        discussion_chat_id: int,
        *,
        limit: int = 10,
    ) -> list[ParticipantStat]:
        safe_limit = max(1, min(int(limit), 100))
        async with self._database._require_pool().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    sender_user_id,
                    MAX(sender_display_name) AS sender_display_name,
                    MAX(sender_username) AS sender_username,
                    COUNT(*) AS message_count,
                    COUNT(*) FILTER (WHERE reply_to_message_id IS NOT NULL)
                        AS reply_count,
                    COALESCE(SUM(reaction_count), 0) AS reactions_received,
                    MAX(posted_at) AS last_message_at
                FROM discussion_messages
                WHERE discussion_chat_id = $1::BIGINT
                  AND sender_kind = 'user'
                GROUP BY sender_user_id
                ORDER BY message_count DESC,
                         reactions_received DESC,
                         last_message_at DESC
                LIMIT $2::INTEGER
                """,
                int(discussion_chat_id),
                safe_limit,
            )
        return [
            ParticipantStat(
                user_id=row["sender_user_id"],
                display_name=str(row["sender_display_name"] or "Без имени"),
                username=row["sender_username"],
                message_count=int(row["message_count"] or 0),
                reply_count=int(row["reply_count"] or 0),
                reactions_received=int(row["reactions_received"] or 0),
                last_message_at=row["last_message_at"],
            )
            for row in rows
        ]


__all__ = ("DiscussionRepository",)
