from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime

from velvet_bot.analytics_dashboard import (
    DashboardPage,
    DashboardRankItem,
    normalize_period,
    period_since,
)
from velvet_bot.database import Database

WEEKDAY_LABELS = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
)


@dataclass(frozen=True, slots=True)
class DiscussionSummary:
    discussion_chat_id: int
    parent_channel_id: int
    linked_threads: int
    total_comments: int
    unique_participants: int
    total_comment_reactions: int
    published_publications: int
    publications_without_comments: int
    average_comments_per_publication: float
    first_comment_at: datetime | None
    last_comment_at: datetime | None


@dataclass(frozen=True, slots=True)
class DiscussedPost:
    post_id: int
    publication_key: str
    posted_at: datetime
    text_content: str
    message_url: str | None
    view_count: int
    channel_reactions: int
    comment_count: int
    first_comment_seconds: int | None
    unique_participants: int
    comment_reactions: int


@dataclass(frozen=True, slots=True)
class DiscussedPostPage:
    items: list[DiscussedPost]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


@dataclass(frozen=True, slots=True)
class ActivityBreakdown:
    weekdays: tuple[int, ...]
    hours: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ActivitySpike:
    day: date
    comment_count: int
    baseline: float
    ratio: float


@dataclass(frozen=True, slots=True)
class RelinkResult:
    roots_marked: int
    comments_linked: int
    threads_linked: int


def format_delay(seconds: int | None) -> str:
    if seconds is None:
        return "—"
    safe = max(0, int(seconds))
    if safe < 60:
        return f"{safe} сек."
    minutes = safe // 60
    if minutes < 60:
        return f"{minutes} мин."
    hours, remaining = divmod(minutes, 60)
    if hours < 24:
        return f"{hours} ч. {remaining} мин." if remaining else f"{hours} ч."
    days, remaining_hours = divmod(hours, 24)
    return (
        f"{days} д. {remaining_hours} ч."
        if remaining_hours
        else f"{days} д."
    )


def _safe_page(page: int, page_size: int, total: int) -> tuple[int, int]:
    safe_size = max(1, min(page_size, 10))
    total_pages = max(1, (total + safe_size - 1) // safe_size)
    return min(max(0, page), total_pages - 1), safe_size


async def get_discussion_summary(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
) -> DiscussionSummary:
    since = period_since(period)
    async with database._require_pool().acquire() as connection:
        comment_row = await connection.fetchrow(
            """
            WITH linked_comments AS (
                SELECT comment.*, source.publication_key
                FROM channel_posts AS comment
                JOIN discussion_threads AS thread
                  ON thread.discussion_chat_id = comment.channel_id
                 AND thread.root_message_id = comment.discussion_root_message_id
                JOIN channel_posts AS source ON source.id = thread.channel_post_id
                WHERE comment.channel_id = $1::BIGINT
                  AND comment.is_discussion_root = FALSE
                  AND comment.discussion_root_message_id IS NOT NULL
                  AND ($2::TIMESTAMPTZ IS NULL OR comment.posted_at >= $2)
            )
            SELECT
                COUNT(*) AS total_comments,
                COUNT(DISTINCT sender_id) FILTER (WHERE sender_id IS NOT NULL)
                    AS unique_participants,
                COALESCE(SUM(reactions_total), 0) AS total_comment_reactions,
                COUNT(DISTINCT publication_key) AS linked_threads,
                MIN(posted_at) AS first_comment_at,
                MAX(posted_at) AS last_comment_at
            FROM linked_comments
            """,
            int(discussion_chat_id),
            since,
        )
        publication_row = await connection.fetchrow(
            """
            WITH publications AS (
                SELECT publication_key
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                  AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
                GROUP BY publication_key
            ),
            comment_counts AS (
                SELECT source.publication_key, COUNT(comment.id) AS comment_count
                FROM discussion_threads AS thread
                JOIN channel_posts AS source ON source.id = thread.channel_post_id
                LEFT JOIN channel_posts AS comment
                  ON comment.channel_id = thread.discussion_chat_id
                 AND comment.discussion_root_message_id = thread.root_message_id
                 AND comment.is_discussion_root = FALSE
                 AND ($2::TIMESTAMPTZ IS NULL OR comment.posted_at >= $2)
                WHERE thread.discussion_chat_id = $3::BIGINT
                GROUP BY source.publication_key
            )
            SELECT
                COUNT(*) AS publication_count,
                COUNT(*) FILTER (WHERE COALESCE(c.comment_count, 0) = 0)
                    AS without_comments,
                COALESCE(AVG(COALESCE(c.comment_count, 0)), 0)
                    AS average_comments
            FROM publications AS p
            LEFT JOIN comment_counts AS c USING (publication_key)
            """,
            int(parent_channel_id),
            since,
            int(discussion_chat_id),
        )
    return DiscussionSummary(
        discussion_chat_id=int(discussion_chat_id),
        parent_channel_id=int(parent_channel_id),
        linked_threads=int(comment_row["linked_threads"] or 0),
        total_comments=int(comment_row["total_comments"] or 0),
        unique_participants=int(comment_row["unique_participants"] or 0),
        total_comment_reactions=int(comment_row["total_comment_reactions"] or 0),
        published_publications=int(publication_row["publication_count"] or 0),
        publications_without_comments=int(publication_row["without_comments"] or 0),
        average_comments_per_publication=float(
            publication_row["average_comments"] or 0
        ),
        first_comment_at=comment_row["first_comment_at"],
        last_comment_at=comment_row["last_comment_at"],
    )


async def list_discussed_posts(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
    page: int,
    page_size: int = 6,
) -> DiscussedPostPage:
    since = period_since(period)
    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                """
                SELECT COUNT(DISTINCT source.publication_key)
                FROM discussion_threads AS thread
                JOIN channel_posts AS source ON source.id = thread.channel_post_id
                JOIN channel_posts AS comment
                  ON comment.channel_id = thread.discussion_chat_id
                 AND comment.discussion_root_message_id = thread.root_message_id
                 AND comment.is_discussion_root = FALSE
                WHERE thread.discussion_chat_id = $1::BIGINT
                  AND source.channel_id = $2::BIGINT
                  AND ($3::TIMESTAMPTZ IS NULL OR comment.posted_at >= $3)
                """,
                int(discussion_chat_id),
                int(parent_channel_id),
                since,
            )
            or 0
        )
        normalized_page, safe_size = _safe_page(page, page_size, total)
        rows = await connection.fetch(
            """
            WITH publications AS (
                SELECT
                    publication_key,
                    MIN(id) AS post_id,
                    MIN(posted_at) AS posted_at,
                    MAX(NULLIF(text_content, '')) AS text_content,
                    MAX(message_url) AS message_url,
                    COALESCE(SUM(view_count), 0) AS view_count,
                    COALESCE(SUM(reactions_total), 0) AS channel_reactions
                FROM channel_posts
                WHERE channel_id = $2::BIGINT
                GROUP BY publication_key
            ),
            thread_map AS (
                SELECT DISTINCT source.publication_key, thread.root_message_id
                FROM discussion_threads AS thread
                JOIN channel_posts AS source ON source.id = thread.channel_post_id
                WHERE thread.discussion_chat_id = $1::BIGINT
                  AND source.channel_id = $2::BIGINT
            ),
            comments AS (
                SELECT
                    map.publication_key,
                    COUNT(comment.id) AS comment_count,
                    MIN(comment.posted_at) AS first_comment_at,
                    COUNT(DISTINCT comment.sender_id) FILTER (
                        WHERE comment.sender_id IS NOT NULL
                    ) AS unique_participants,
                    COALESCE(SUM(comment.reactions_total), 0) AS comment_reactions
                FROM thread_map AS map
                JOIN channel_posts AS comment
                  ON comment.channel_id = $1::BIGINT
                 AND comment.discussion_root_message_id = map.root_message_id
                 AND comment.is_discussion_root = FALSE
                WHERE $3::TIMESTAMPTZ IS NULL OR comment.posted_at >= $3
                GROUP BY map.publication_key
            )
            SELECT
                publication.post_id,
                publication.publication_key,
                publication.posted_at,
                COALESCE(publication.text_content, '') AS text_content,
                publication.message_url,
                publication.view_count,
                publication.channel_reactions,
                comments.comment_count,
                GREATEST(
                    0,
                    EXTRACT(EPOCH FROM (
                        comments.first_comment_at - publication.posted_at
                    ))::BIGINT
                ) AS first_comment_seconds,
                comments.unique_participants,
                comments.comment_reactions
            FROM comments
            JOIN publications AS publication USING (publication_key)
            ORDER BY comments.comment_count DESC,
                     comments.comment_reactions DESC,
                     publication.posted_at DESC
            OFFSET $4::INTEGER
            LIMIT $5::INTEGER
            """,
            int(discussion_chat_id),
            int(parent_channel_id),
            since,
            normalized_page * safe_size,
            safe_size,
        )
    return DiscussedPostPage(
        items=[
            DiscussedPost(
                post_id=int(row["post_id"]),
                publication_key=str(row["publication_key"]),
                posted_at=row["posted_at"],
                text_content=str(row["text_content"] or ""),
                message_url=row["message_url"],
                view_count=int(row["view_count"] or 0),
                channel_reactions=int(row["channel_reactions"] or 0),
                comment_count=int(row["comment_count"] or 0),
                first_comment_seconds=(
                    int(row["first_comment_seconds"])
                    if row["first_comment_seconds"] is not None
                    else None
                ),
                unique_participants=int(row["unique_participants"] or 0),
                comment_reactions=int(row["comment_reactions"] or 0),
            )
            for row in rows
        ],
        page=normalized_page,
        page_size=safe_size,
        total_items=total,
    )


async def get_discussed_post(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    post_id: int,
    *,
    period: str,
) -> DiscussedPost | None:
    since = period_since(period)
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            WITH selected AS (
                SELECT publication_key
                FROM channel_posts
                WHERE id = $3::BIGINT
                  AND channel_id = $2::BIGINT
            ),
            publication AS (
                SELECT
                    MIN(id) AS post_id,
                    publication_key,
                    MIN(posted_at) AS posted_at,
                    MAX(NULLIF(text_content, '')) AS text_content,
                    MAX(message_url) AS message_url,
                    COALESCE(SUM(view_count), 0) AS view_count,
                    COALESCE(SUM(reactions_total), 0) AS channel_reactions
                FROM channel_posts
                WHERE channel_id = $2::BIGINT
                  AND publication_key = (SELECT publication_key FROM selected)
                GROUP BY publication_key
            ),
            roots AS (
                SELECT DISTINCT thread.root_message_id
                FROM discussion_threads AS thread
                JOIN channel_posts AS source ON source.id = thread.channel_post_id
                WHERE thread.discussion_chat_id = $1::BIGINT
                  AND source.channel_id = $2::BIGINT
                  AND source.publication_key = (SELECT publication_key FROM selected)
            ),
            comments AS (
                SELECT
                    COUNT(*) AS comment_count,
                    MIN(posted_at) AS first_comment_at,
                    COUNT(DISTINCT sender_id) FILTER (WHERE sender_id IS NOT NULL)
                        AS unique_participants,
                    COALESCE(SUM(reactions_total), 0) AS comment_reactions
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                  AND is_discussion_root = FALSE
                  AND discussion_root_message_id IN (SELECT root_message_id FROM roots)
                  AND ($4::TIMESTAMPTZ IS NULL OR posted_at >= $4)
            )
            SELECT
                publication.*,
                comments.comment_count,
                CASE
                    WHEN comments.first_comment_at IS NULL THEN NULL
                    ELSE GREATEST(
                        0,
                        EXTRACT(EPOCH FROM (
                            comments.first_comment_at - publication.posted_at
                        ))::BIGINT
                    )
                END AS first_comment_seconds,
                comments.unique_participants,
                comments.comment_reactions
            FROM publication
            CROSS JOIN comments
            """,
            int(discussion_chat_id),
            int(parent_channel_id),
            int(post_id),
            since,
        )
    if row is None:
        return None
    return DiscussedPost(
        post_id=int(row["post_id"]),
        publication_key=str(row["publication_key"]),
        posted_at=row["posted_at"],
        text_content=str(row["text_content"] or ""),
        message_url=row["message_url"],
        view_count=int(row["view_count"] or 0),
        channel_reactions=int(row["channel_reactions"] or 0),
        comment_count=int(row["comment_count"] or 0),
        first_comment_seconds=(
            int(row["first_comment_seconds"])
            if row["first_comment_seconds"] is not None
            else None
        ),
        unique_participants=int(row["unique_participants"] or 0),
        comment_reactions=int(row["comment_reactions"] or 0),
    )


async def _rank_page(
    database: Database,
    count_sql: str,
    rows_sql: str,
    args: tuple[object, ...],
    *,
    page: int,
    page_size: int = 8,
) -> DashboardPage:
    async with database._require_pool().acquire() as connection:
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


async def list_active_participants(
    database: Database,
    discussion_chat_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    since = period_since(period)
    where = """
        channel_id = $1::BIGINT
        AND is_discussion_root = FALSE
        AND discussion_root_message_id IS NOT NULL
        AND sender_id IS NOT NULL
        AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
    """
    return await _rank_page(
        database,
        f"SELECT COUNT(DISTINCT sender_id) FROM channel_posts WHERE {where}",
        f"""
        SELECT
            sender_id AS item_key,
            COALESCE(MAX(sender_name), sender_id) AS item_label,
            COUNT(*) AS item_count,
            COUNT(*) FILTER (WHERE reply_to_message_id IS NOT NULL)
                AS secondary_count,
            NULL::TEXT AS detail
        FROM channel_posts
        WHERE {where}
        GROUP BY sender_id
        ORDER BY item_count DESC, item_label
        OFFSET $3::INTEGER
        LIMIT $4::INTEGER
        """,
        (int(discussion_chat_id), since),
        page=page,
    )


async def list_most_replied_participants(
    database: Database,
    discussion_chat_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    since = period_since(period)
    count_sql = """
        SELECT COUNT(DISTINCT parent.sender_id)
        FROM channel_posts AS child
        JOIN channel_posts AS parent
          ON parent.channel_id = child.channel_id
         AND parent.message_id = child.reply_to_message_id
        WHERE child.channel_id = $1::BIGINT
          AND child.is_discussion_root = FALSE
          AND parent.is_discussion_root = FALSE
          AND parent.sender_id IS NOT NULL
          AND ($2::TIMESTAMPTZ IS NULL OR child.posted_at >= $2)
    """
    rows_sql = """
        SELECT
            parent.sender_id AS item_key,
            COALESCE(MAX(parent.sender_name), parent.sender_id) AS item_label,
            COUNT(*) AS item_count,
            COUNT(DISTINCT child.sender_id) FILTER (WHERE child.sender_id IS NOT NULL)
                AS secondary_count,
            NULL::TEXT AS detail
        FROM channel_posts AS child
        JOIN channel_posts AS parent
          ON parent.channel_id = child.channel_id
         AND parent.message_id = child.reply_to_message_id
        WHERE child.channel_id = $1::BIGINT
          AND child.is_discussion_root = FALSE
          AND parent.is_discussion_root = FALSE
          AND parent.sender_id IS NOT NULL
          AND ($2::TIMESTAMPTZ IS NULL OR child.posted_at >= $2)
        GROUP BY parent.sender_id
        ORDER BY item_count DESC, item_label
        OFFSET $3::INTEGER
        LIMIT $4::INTEGER
    """
    return await _rank_page(
        database,
        count_sql,
        rows_sql,
        (int(discussion_chat_id), since),
        page=page,
    )


async def list_reaction_leaders(
    database: Database,
    discussion_chat_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    since = period_since(period)
    where = """
        channel_id = $1::BIGINT
        AND is_discussion_root = FALSE
        AND discussion_root_message_id IS NOT NULL
        AND sender_id IS NOT NULL
        AND reactions_total > 0
        AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
    """
    return await _rank_page(
        database,
        f"SELECT COUNT(DISTINCT sender_id) FROM channel_posts WHERE {where}",
        f"""
        SELECT
            sender_id AS item_key,
            COALESCE(MAX(sender_name), sender_id) AS item_label,
            COALESCE(SUM(reactions_total), 0) AS item_count,
            COUNT(*) FILTER (WHERE reactions_total > 0) AS secondary_count,
            NULL::TEXT AS detail
        FROM channel_posts
        WHERE {where}
        GROUP BY sender_id
        ORDER BY item_count DESC, secondary_count DESC, item_label
        OFFSET $3::INTEGER
        LIMIT $4::INTEGER
        """,
        (int(discussion_chat_id), since),
        page=page,
    )


async def list_discussed_characters(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    since = period_since(period)
    base = """
        WITH publication_characters AS (
            SELECT DISTINCT source.publication_key, character.id, character.name,
                            character.universe
            FROM channel_posts AS source
            JOIN channel_post_hashtags AS hashtag ON hashtag.post_id = source.id
            JOIN characters AS character ON character.id = hashtag.character_id
            WHERE source.channel_id = $2::BIGINT
        ),
        comment_publications AS (
            SELECT comment.id, source.publication_key
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
        SELECT COUNT(DISTINCT character.id)
        FROM publication_characters AS character
        JOIN comment_publications AS comment USING (publication_key)
    """
    rows_sql = base + """
        SELECT
            character.id::TEXT AS item_key,
            character.name AS item_label,
            COUNT(comment.id) AS item_count,
            COUNT(DISTINCT character.publication_key) AS secondary_count,
            character.universe AS detail
        FROM publication_characters AS character
        JOIN comment_publications AS comment USING (publication_key)
        GROUP BY character.id, character.name, character.universe
        ORDER BY item_count DESC, secondary_count DESC, item_label
        OFFSET $4::INTEGER
        LIMIT $5::INTEGER
    """
    return await _rank_page(
        database,
        count_sql,
        rows_sql,
        (int(discussion_chat_id), int(parent_channel_id), since),
        page=page,
    )


async def list_discussed_universes(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    since = period_since(period)
    base = """
        WITH publication_universes AS (
            SELECT DISTINCT source.publication_key, character.universe
            FROM channel_posts AS source
            JOIN channel_post_hashtags AS hashtag ON hashtag.post_id = source.id
            JOIN characters AS character ON character.id = hashtag.character_id
            WHERE source.channel_id = $2::BIGINT
              AND character.universe IS NOT NULL
        ),
        comment_publications AS (
            SELECT comment.id, source.publication_key
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
    return await _rank_page(
        database,
        base + """
            SELECT COUNT(DISTINCT universe)
            FROM publication_universes
        """,
        base + """
            SELECT
                universe AS item_key,
                universe AS item_label,
                COUNT(comment.id) AS item_count,
                COUNT(DISTINCT publication_universes.publication_key)
                    AS secondary_count,
                NULL::TEXT AS detail
            FROM publication_universes
            JOIN comment_publications AS comment USING (publication_key)
            GROUP BY universe
            ORDER BY item_count DESC, secondary_count DESC, item_label
            OFFSET $4::INTEGER
            LIMIT $5::INTEGER
        """,
        (int(discussion_chat_id), int(parent_channel_id), since),
        page=page,
    )


async def list_discussed_stories(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
    page: int,
) -> DashboardPage:
    since = period_since(period)
    base = """
        WITH character_story_map AS (
            SELECT character_id, story_id FROM character_story_links
            UNION
            SELECT id AS character_id, story_id
            FROM characters
            WHERE story_id IS NOT NULL
        ),
        publication_stories AS (
            SELECT DISTINCT source.publication_key, story.id, story.short_label,
                            story.title, story.universe
            FROM channel_posts AS source
            JOIN channel_post_hashtags AS hashtag ON hashtag.post_id = source.id
            JOIN character_story_map AS mapping
              ON mapping.character_id = hashtag.character_id
            JOIN character_stories AS story ON story.id = mapping.story_id
            WHERE source.channel_id = $2::BIGINT
        ),
        comment_publications AS (
            SELECT comment.id, source.publication_key
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
    return await _rank_page(
        database,
        base + "SELECT COUNT(DISTINCT id) FROM publication_stories",
        base + """
            SELECT
                story.id::TEXT AS item_key,
                COALESCE(story.short_label, story.title) AS item_label,
                COUNT(comment.id) AS item_count,
                COUNT(DISTINCT story.publication_key) AS secondary_count,
                story.universe || ' · ' || story.title AS detail
            FROM publication_stories AS story
            JOIN comment_publications AS comment USING (publication_key)
            GROUP BY story.id, story.short_label, story.title, story.universe
            ORDER BY item_count DESC, secondary_count DESC, item_label
            OFFSET $4::INTEGER
            LIMIT $5::INTEGER
        """,
        (int(discussion_chat_id), int(parent_channel_id), since),
        page=page,
    )


async def list_publications_without_comments(
    database: Database,
    discussion_chat_id: int,
    parent_channel_id: int,
    *,
    period: str,
    page: int,
    page_size: int = 8,
) -> DashboardPage:
    since = period_since(period)
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
        WHERE publication_key NOT IN (SELECT publication_key FROM commented)
    """
    rows_sql = base + """
        SELECT
            post_id::TEXT AS item_key,
            COALESCE(
                NULLIF(LEFT(REGEXP_REPLACE(text_content, E'[\\n\\r]+', ' ', 'g'), 72), ''),
                'Публикация без текста'
            ) AS item_label,
            0 AS item_count,
            0 AS secondary_count,
            TO_CHAR(posted_at AT TIME ZONE 'Europe/Berlin', 'DD.MM.YYYY HH24:MI')
                AS detail
        FROM publications
        WHERE publication_key NOT IN (SELECT publication_key FROM commented)
        ORDER BY posted_at DESC
        OFFSET $4::INTEGER
        LIMIT $5::INTEGER
    """
    return await _rank_page(
        database,
        count_sql,
        rows_sql,
        (int(discussion_chat_id), int(parent_channel_id), since),
        page=page,
        page_size=page_size,
    )


async def get_activity_breakdown(
    database: Database,
    discussion_chat_id: int,
    *,
    period: str,
    timezone_name: str,
) -> ActivityBreakdown:
    since = period_since(period)
    async with database._require_pool().acquire() as connection:
        weekday_rows = await connection.fetch(
            """
            SELECT
                EXTRACT(ISODOW FROM timezone($3::TEXT, posted_at))::INTEGER AS bucket,
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
                EXTRACT(HOUR FROM timezone($3::TEXT, posted_at))::INTEGER AS bucket,
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
        bucket = int(row["bucket"] or -1)
        if 0 <= bucket <= 23:
            hours[bucket] = int(row["item_count"] or 0)
    return ActivityBreakdown(weekdays=tuple(weekdays), hours=tuple(hours))


async def list_activity_spikes(
    database: Database,
    discussion_chat_id: int,
    *,
    period: str,
    timezone_name: str,
) -> list[ActivitySpike]:
    since = period_since(period)
    async with database._require_pool().acquire() as connection:
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
    values = [int(row["comment_count"] or 0) for row in rows]
    if len(values) < 3:
        return []
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    deviation = math.sqrt(variance)
    threshold = max(5.0, mean * 1.8, mean + 2 * deviation)
    spikes = [
        ActivitySpike(
            day=row["activity_day"],
            comment_count=int(row["comment_count"] or 0),
            baseline=mean,
            ratio=(int(row["comment_count"] or 0) / mean if mean > 0 else 0.0),
        )
        for row in rows
        if int(row["comment_count"] or 0) >= threshold
    ]
    return sorted(spikes, key=lambda item: (-item.comment_count, item.day))[:10]


async def rebuild_discussion_threads(
    database: Database,
    discussion_chat_id: int,
) -> RelinkResult:
    async with database._require_pool().acquire() as connection:
        async with connection.transaction():
            roots_status = await connection.execute(
                """
                WITH candidates AS (
                    SELECT post.id
                    FROM channel_posts AS post
                    JOIN tracked_channels AS discussion
                      ON discussion.chat_id = post.channel_id
                     AND discussion.source_kind = 'discussion'
                    WHERE post.channel_id = $1::BIGINT
                      AND post.reply_to_message_id IS NULL
                      AND (
                          post.sender_id LIKE 'channel%'
                          OR post.sender_id LIKE 'chat%'
                          OR EXISTS (
                              SELECT 1
                              FROM tracked_channels AS parent
                              WHERE parent.chat_id = discussion.parent_channel_id
                                AND parent.title IS NOT NULL
                                AND post.sender_name IS NOT NULL
                                AND LOWER(parent.title) = LOWER(post.sender_name)
                          )
                      )
                      AND EXISTS (
                          SELECT 1
                          FROM channel_posts AS child
                          WHERE child.channel_id = post.channel_id
                            AND child.reply_to_message_id = post.message_id
                      )
                )
                UPDATE channel_posts AS post
                SET is_discussion_root = TRUE,
                    discussion_root_message_id = post.message_id
                FROM candidates
                WHERE post.id = candidates.id
                  AND (
                      post.is_discussion_root = FALSE
                      OR post.discussion_root_message_id IS DISTINCT FROM post.message_id
                  )
                """,
                int(discussion_chat_id),
            )
            comments_status = await connection.execute(
                """
                WITH RECURSIVE reply_tree AS (
                    SELECT channel_id, message_id, message_id AS root_message_id
                    FROM channel_posts
                    WHERE channel_id = $1::BIGINT
                      AND is_discussion_root = TRUE

                    UNION

                    SELECT child.channel_id, child.message_id, parent.root_message_id
                    FROM channel_posts AS child
                    JOIN reply_tree AS parent
                      ON parent.channel_id = child.channel_id
                     AND parent.message_id = child.reply_to_message_id
                )
                UPDATE channel_posts AS target
                SET discussion_root_message_id = reply_tree.root_message_id
                FROM reply_tree
                WHERE target.channel_id = reply_tree.channel_id
                  AND target.message_id = reply_tree.message_id
                  AND target.discussion_root_message_id IS DISTINCT FROM reply_tree.root_message_id
                """,
                int(discussion_chat_id),
            )
            threads_status = await connection.execute(
                """
                INSERT INTO discussion_threads (
                    discussion_chat_id,
                    root_message_id,
                    parent_channel_id,
                    channel_message_id,
                    channel_post_id,
                    link_source,
                    updated_at
                )
                SELECT
                    root.channel_id,
                    root.message_id,
                    discussion.parent_channel_id,
                    matched.message_id,
                    matched.id,
                    'rebuild_exact_text',
                    NOW()
                FROM channel_posts AS root
                JOIN tracked_channels AS discussion
                  ON discussion.chat_id = root.channel_id
                 AND discussion.source_kind = 'discussion'
                 AND discussion.parent_channel_id IS NOT NULL
                JOIN LATERAL (
                    SELECT candidate.id, candidate.message_id
                    FROM channel_posts AS candidate
                    WHERE candidate.channel_id = discussion.parent_channel_id
                      AND NULLIF(BTRIM(root.text_content), '') IS NOT NULL
                      AND candidate.text_content = root.text_content
                      AND ABS(EXTRACT(EPOCH FROM (
                          candidate.posted_at - root.posted_at
                      ))) <= 3600
                    ORDER BY ABS(EXTRACT(EPOCH FROM (
                                 candidate.posted_at - root.posted_at
                             ))),
                             candidate.id
                    LIMIT 1
                ) AS matched ON TRUE
                WHERE root.channel_id = $1::BIGINT
                  AND root.is_discussion_root = TRUE
                ON CONFLICT (discussion_chat_id, root_message_id) DO UPDATE
                SET parent_channel_id = EXCLUDED.parent_channel_id,
                    channel_message_id = COALESCE(
                        discussion_threads.channel_message_id,
                        EXCLUDED.channel_message_id
                    ),
                    channel_post_id = COALESCE(
                        discussion_threads.channel_post_id,
                        EXCLUDED.channel_post_id
                    ),
                    link_source = CASE
                        WHEN discussion_threads.channel_post_id IS NULL
                            THEN EXCLUDED.link_source
                        ELSE discussion_threads.link_source
                    END,
                    updated_at = NOW()
                """,
                int(discussion_chat_id),
            )
            await connection.execute(
                """
                UPDATE discussion_threads AS thread
                SET channel_post_id = source.id,
                    updated_at = NOW()
                FROM channel_posts AS source
                WHERE thread.discussion_chat_id = $1::BIGINT
                  AND thread.channel_post_id IS NULL
                  AND thread.channel_message_id IS NOT NULL
                  AND source.channel_id = thread.parent_channel_id
                  AND source.message_id = thread.channel_message_id
                """,
                int(discussion_chat_id),
            )

    def affected(status: str) -> int:
        try:
            return int(status.rsplit(" ", 1)[-1])
        except (TypeError, ValueError):
            return 0

    return RelinkResult(
        roots_marked=affected(roots_status),
        comments_linked=affected(comments_status),
        threads_linked=affected(threads_status),
    )
