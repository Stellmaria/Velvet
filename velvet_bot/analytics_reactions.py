from __future__ import annotations

import json

from velvet_bot.database import Database


async def set_analytics_reaction_counts(
    database: Database,
    *,
    chat_id: int,
    message_id: int,
    breakdown: dict[str, int],
) -> bool:
    clean = {
        str(key): max(0, int(value))
        for key, value in breakdown.items()
        if int(value) > 0
    }
    async with database._require_pool().acquire() as connection:
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
            int(chat_id),
            int(message_id),
            sum(clean.values()),
            json.dumps(clean, ensure_ascii=False),
        )
    return updated is not None
