from __future__ import annotations

from velvet_bot.analytics_dashboard import DiscussionDashboard, period_since
from velvet_bot.database import Database


async def get_discussion_dashboard_compat(
    database: Database,
    chat_id: int,
    *,
    period: str,
) -> DiscussionDashboard:
    """Preserve the Phase 1 dashboard query for callers importing the old helper."""
    since = period_since(period)
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                COALESCE(MAX(t.title), t.chat_id::TEXT) AS title,
                COUNT(p.id) AS total_messages,
                COUNT(DISTINCT p.sender_id) FILTER (WHERE p.sender_id IS NOT NULL)
                    AS unique_participants,
                COUNT(p.id) FILTER (WHERE p.reply_to_message_id IS NOT NULL)
                    AS reply_messages,
                COUNT(p.id) FILTER (WHERE p.media_type <> 'text') AS media_messages,
                COUNT(p.id) FILTER (WHERE p.has_spoiler) AS spoiler_messages,
                COUNT(p.id) FILTER (WHERE p.is_prompt) AS prompt_messages,
                COALESCE(SUM(p.reactions_total), 0) AS total_reactions,
                MIN(p.posted_at) AS first_message_at,
                MAX(p.posted_at) AS last_message_at
            FROM tracked_channels AS t
            LEFT JOIN channel_posts AS p
                ON p.channel_id = t.chat_id
               AND ($2::TIMESTAMPTZ IS NULL OR p.posted_at >= $2)
            WHERE t.chat_id = $1::BIGINT
            GROUP BY t.chat_id
            """,
            int(chat_id),
            since,
        )
    return DiscussionDashboard(
        chat_id=int(chat_id),
        title=str(row["title"] if row else chat_id),
        total_messages=int(row["total_messages"] or 0) if row else 0,
        unique_participants=int(row["unique_participants"] or 0) if row else 0,
        reply_messages=int(row["reply_messages"] or 0) if row else 0,
        media_messages=int(row["media_messages"] or 0) if row else 0,
        spoiler_messages=int(row["spoiler_messages"] or 0) if row else 0,
        prompt_messages=int(row["prompt_messages"] or 0) if row else 0,
        total_reactions=int(row["total_reactions"] or 0) if row else 0,
        first_message_at=row["first_message_at"] if row else None,
        last_message_at=row["last_message_at"] if row else None,
    )
