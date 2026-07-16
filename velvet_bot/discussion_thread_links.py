from __future__ import annotations

from velvet_bot.database import Database


async def link_pending_threads_for_channel_post(
    database: Database,
    *,
    channel_id: int,
    message_id: int,
) -> int:
    """Attach discussion roots that arrived before the matching channel post."""
    async with database._require_pool().acquire() as connection:
        status = await connection.execute(
            """
            UPDATE discussion_threads AS thread
            SET channel_post_id = source.id,
                link_source = CASE
                    WHEN thread.link_source LIKE 'pending%'
                        THEN 'live_forward'
                    ELSE thread.link_source
                END,
                updated_at = NOW()
            FROM channel_posts AS source
            WHERE thread.parent_channel_id = $1::BIGINT
              AND thread.channel_message_id = $2::BIGINT
              AND thread.channel_post_id IS NULL
              AND source.channel_id = $1::BIGINT
              AND source.message_id = $2::BIGINT
            """,
            int(channel_id),
            int(message_id),
        )
    try:
        return int(status.rsplit(" ", 1)[-1])
    except (TypeError, ValueError):
        return 0
