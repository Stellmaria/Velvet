from __future__ import annotations

from datetime import datetime

from velvet_bot.analytics_dashboard import DashboardPage, DashboardRankItem
from velvet_bot.database import Database
from velvet_bot.domains.discussions.insight_models import (
    ActivityBreakdown,
    DailyActivityCount,
)


def _safe_page(page: int, page_size: int, total: int) -> tuple[int, int]:
    safe_size = max(1, min(int(page_size), 10))
    total_pages = max(1, (total + safe_size - 1) // safe_size)
    return min(max(0, int(page)), total_pages - 1), safe_size


class DiscussionActivityRepository:
    """PostgreSQL queries for silent publications and temporal activity."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_publications_without_comments(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        since: datetime | None,
        page: int,
        page_size: int = 8,
    ) -> DashboardPage:
        base = """
            WITH publications AS (
                SELECT
                    publication_key,
                    MIN(id) AS post_id,
                    MIN(posted_at) AS posted_at,
                    MAX(NULLIF(text_content, '')) AS text_content
                FROM channel_posts
                WHERE channel_id = $2::BIGINT
                  AND ($3::TIMESTAMPTZ IS NULL OR posted_at >= $3)
                GROUP BY publication_key
            ),
            commented AS (
                SELECT DISTINCT source.publication_key
                FROM discussion_threads AS thread
                JOIN channel_posts AS source ON source.id = thread.channel_post_id
                JOIN channel_posts AS comment
                  ON comment.channel_id = thread.discussion_chat_id
                 AND comment.discussion_root_message_id = thread.root_message_id
                 AND comment.is_discussion_root = FALSE
                WHERE thread.discussion_chat_id = $1::BIGINT
                  AND ($3::TIMESTAMPTZ IS NULL OR comment.posted_at >= $3)
            )
        """
        count_sql = base + """
            SELECT COUNT(*)
            FROM publications
            WHERE publication_key NOT IN (
                SELECT publication_key FROM commented
            )
        """
        rows_sql = base + """
            SELECT
                post_id::TEXT AS item_key,
                COALESCE(
                    NULLIF(
                        LEFT(
                            REGEXP_REPLACE(text_content, E'[\n\r]+', ' ', 'g'),
                            72
                        ),
                        ''
                    ),
                    'Публикация без текста'
                ) AS item_label,
                0 AS item_count,
                0 AS secondary_count,
                TO_CHAR(
                    posted_at AT TIME ZONE 'Europe/Berlin',
                    'DD.MM.YYYY HH24:MI'
                ) AS detail
            FROM publications
            WHERE publication_key NOT IN (
                SELECT publication_key FROM commented
            )
            ORDER BY posted_at DESC
            OFFSET $4::INTEGER
            LIMIT $5::INTEGER
        """
        async with self._database._require_pool().acquire() as connection:
            args = (
                int(discussion_chat_id),
                int(parent_channel_id),
                since,
            )
            total = int(await connection.fetchval(count_sql, *args) or 0)
            normalized_page, safe_size = _safe_page(page, page_size, total)
            rows = await connection.fetch(
                rows_sql,
                *args,
                normalized_page * safe_size,
                safe_size,
            )
        return DashboardPage(
            items=[
                DashboardRankItem(
                    key=str(row["item_key"]),
                    label=str(row["item_label"]),
                    count=int(row["item_count"] or 0),
                    secondary_count=int(row["secondary_count"] or 0),
                    detail=(str(row["detail"]) if row["detail"] else None),
                )
                for row in rows
            ],
            page=normalized_page,
            page_size=safe_size,
            total_items=total,
        )

    async def get_activity_breakdown(
        self,
        *,
        discussion_chat_id: int,
        since: datetime | None,
        timezone_name: str,
    ) -> ActivityBreakdown:
        async with self._database._require_pool().acquire() as connection:
            weekday_rows = await connection.fetch(
                """
                SELECT
                    EXTRACT(
                        ISODOW FROM timezone($3::TEXT, posted_at)
                    )::INTEGER AS bucket,
                    COUNT(*) AS item_count
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                  AND is_discussion_root = FALSE
                  AND discussion_root_message_id IS NOT NULL
                  AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
                GROUP BY bucket
                ORDER BY bucket
                """,
                int(discussion_chat_id),
                since,
                timezone_name,
            )
            hour_rows = await connection.fetch(
                """
                SELECT
                    EXTRACT(
                        HOUR FROM timezone($3::TEXT, posted_at)
                    )::INTEGER AS bucket,
                    COUNT(*) AS item_count
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                  AND is_discussion_root = FALSE
                  AND discussion_root_message_id IS NOT NULL
                  AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
                GROUP BY bucket
                ORDER BY bucket
                """,
                int(discussion_chat_id),
                since,
                timezone_name,
            )
        weekdays = [0] * 7
        hours = [0] * 24
        for row in weekday_rows:
            bucket = int(row["bucket"] or 0)
            if 1 <= bucket <= 7:
                weekdays[bucket - 1] = int(row["item_count"] or 0)
        for row in hour_rows:
            bucket = int(row["bucket"] if row["bucket"] is not None else -1)
            if 0 <= bucket <= 23:
                hours[bucket] = int(row["item_count"] or 0)
        return ActivityBreakdown(
            weekdays=tuple(weekdays),
            hours=tuple(hours),
        )

    async def list_daily_activity(
        self,
        *,
        discussion_chat_id: int,
        since: datetime | None,
        timezone_name: str,
    ) -> list[DailyActivityCount]:
        async with self._database._require_pool().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT
                    timezone($3::TEXT, posted_at)::DATE AS activity_day,
                    COUNT(*) AS comment_count
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                  AND is_discussion_root = FALSE
                  AND discussion_root_message_id IS NOT NULL
                  AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
                GROUP BY activity_day
                ORDER BY activity_day
                """,
                int(discussion_chat_id),
                since,
                timezone_name,
            )
        return [
            DailyActivityCount(
                day=row["activity_day"],
                comment_count=int(row["comment_count"] or 0),
            )
            for row in rows
        ]


__all__ = ("DiscussionActivityRepository",)
