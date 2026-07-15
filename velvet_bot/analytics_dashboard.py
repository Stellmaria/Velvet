from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from velvet_bot.database import Database

PERIOD_LABELS = {
    "all": "всё время",
    "7d": "7 дней",
    "30d": "30 дней",
}
PERIOD_DAYS = {"all": None, "7d": 7, "30d": 30}


@dataclass(frozen=True, slots=True)
class DashboardOverview:
    channel_id: int
    total_messages: int
    total_publications: int
    prompt_publications: int
    media_messages: int
    spoiler_messages: int
    edited_messages: int
    unique_characters: int
    unique_hashtags: int
    total_reactions: int
    captured_views: int
    captured_forwards: int
    average_text_length: float
    first_post_at: datetime | None
    last_post_at: datetime | None


@dataclass(frozen=True, slots=True)
class DashboardRankItem:
    key: str
    label: str
    count: int
    secondary_count: int = 0
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class DashboardPage:
    items: list[DashboardRankItem]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


@dataclass(frozen=True, slots=True)
class PromptDashboard:
    total: int
    with_important: int
    with_strict: int
    with_negative: int
    with_technical: int
    with_palette: int
    average_length: float


@dataclass(frozen=True, slots=True)
class DiscussionSource:
    chat_id: int
    title: str


@dataclass(frozen=True, slots=True)
class DiscussionDashboard:
    chat_id: int
    title: str
    total_messages: int
    unique_participants: int
    reply_messages: int
    media_messages: int
    spoiler_messages: int
    prompt_messages: int
    total_reactions: int
    first_message_at: datetime | None
    last_message_at: datetime | None


def normalize_period(value: str) -> str:
    return value if value in PERIOD_DAYS else "all"


def period_since(value: str) -> datetime | None:
    period = normalize_period(value)
    days = PERIOD_DAYS[period]
    if days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=days)


async def get_dashboard_overview(
    database: Database,
    channel_id: int,
    *,
    period: str,
) -> DashboardOverview:
    since = period_since(period)
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                COUNT(*) AS total_messages,
                COUNT(DISTINCT publication_key) AS total_publications,
                COUNT(DISTINCT publication_key) FILTER (WHERE is_prompt)
                    AS prompt_publications,
                COUNT(*) FILTER (WHERE media_type <> 'text') AS media_messages,
                COUNT(*) FILTER (WHERE has_spoiler) AS spoiler_messages,
                COUNT(*) FILTER (WHERE edited_at IS NOT NULL) AS edited_messages,
                COALESCE(SUM(reactions_total), 0) AS total_reactions,
                COALESCE(SUM(view_count), 0) AS captured_views,
                COALESCE(SUM(forward_count), 0) AS captured_forwards,
                COALESCE(AVG(text_length) FILTER (WHERE text_length > 0), 0)
                    AS average_text_length,
                MIN(posted_at) AS first_post_at,
                MAX(posted_at) AS last_post_at
            FROM channel_posts
            WHERE channel_id = $1
              AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
            """,
            channel_id,
            since,
        )
        relation = await connection.fetchrow(
            """
            SELECT
                COUNT(DISTINCT h.character_id) FILTER (
                    WHERE h.character_id IS NOT NULL
                ) AS unique_characters,
                COUNT(DISTINCT h.normalized_hashtag) AS unique_hashtags
            FROM channel_post_hashtags AS h
            JOIN channel_posts AS p ON p.id = h.post_id
            WHERE p.channel_id = $1
              AND ($2::TIMESTAMPTZ IS NULL OR p.posted_at >= $2)
            """,
            channel_id,
            since,
        )
    return DashboardOverview(
        channel_id=channel_id,
        total_messages=int(row["total_messages"] or 0),
        total_publications=int(row["total_publications"] or 0),
        prompt_publications=int(row["prompt_publications"] or 0),
        media_messages=int(row["media_messages"] or 0),
        spoiler_messages=int(row["spoiler_messages"] or 0),
        edited_messages=int(row["edited_messages"] or 0),
        unique_characters=int(relation["unique_characters"] or 0),
        unique_hashtags=int(relation["unique_hashtags"] or 0),
        total_reactions=int(row["total_reactions"] or 0),
        captured_views=int(row["captured_views"] or 0),
        captured_forwards=int(row["captured_forwards"] or 0),
        average_text_length=float(row["average_text_length"] or 0),
        first_post_at=row["first_post_at"],
        last_post_at=row["last_post_at"],
    )


async def get_prompt_dashboard(
    database: Database,
    channel_id: int,
    *,
    period: str,
) -> PromptDashboard:
    since = period_since(period)
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                COUNT(DISTINCT publication_key) FILTER (WHERE is_prompt) AS total,
                COUNT(DISTINCT publication_key) FILTER (
                    WHERE is_prompt AND has_important_section
                ) AS with_important,
                COUNT(DISTINCT publication_key) FILTER (
                    WHERE is_prompt AND has_strict_section
                ) AS with_strict,
                COUNT(DISTINCT publication_key) FILTER (
                    WHERE is_prompt AND has_negative_section
                ) AS with_negative,
                COUNT(DISTINCT publication_key) FILTER (
                    WHERE is_prompt AND has_technical_section
                ) AS with_technical,
                COUNT(DISTINCT publication_key) FILTER (
                    WHERE is_prompt AND has_palette
                ) AS with_palette,
                COALESCE(AVG(text_length) FILTER (WHERE is_prompt), 0)
                    AS average_length
            FROM channel_posts
            WHERE channel_id = $1
              AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
            """,
            channel_id,
            since,
        )
    return PromptDashboard(
        total=int(row["total"] or 0),
        with_important=int(row["with_important"] or 0),
        with_strict=int(row["with_strict"] or 0),
        with_negative=int(row["with_negative"] or 0),
        with_technical=int(row["with_technical"] or 0),
        with_palette=int(row["with_palette"] or 0),
        average_length=float(row["average_length"] or 0),
    )


async def list_hashtag_dashboard(
    database: Database,
    channel_id: int,
    *,
    period: str,
    page: int,
    page_size: int = 8,
    unresolved_only: bool = False,
) -> DashboardPage:
    since = period_since(period)
    safe_size = max(1, min(page_size, 10))
    safe_page = max(0, page)
    character_filter = "AND h.character_id IS NULL" if unresolved_only else ""
    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                f"""
                SELECT COUNT(DISTINCT h.normalized_hashtag)
                FROM channel_post_hashtags AS h
                JOIN channel_posts AS p ON p.id = h.post_id
                WHERE p.channel_id = $1
                  AND ($2::TIMESTAMPTZ IS NULL OR p.posted_at >= $2)
                  {character_filter}
                """,
                channel_id,
                since,
            )
            or 0
        )
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            f"""
            SELECT
                h.normalized_hashtag,
                MAX(h.hashtag) AS hashtag,
                COUNT(DISTINCT p.publication_key) AS publication_count,
                COUNT(DISTINCT p.publication_key) FILTER (WHERE p.is_prompt)
                    AS prompt_count,
                MAX(c.name) AS character_name
            FROM channel_post_hashtags AS h
            JOIN channel_posts AS p ON p.id = h.post_id
            LEFT JOIN characters AS c ON c.id = h.character_id
            WHERE p.channel_id = $1
              AND ($2::TIMESTAMPTZ IS NULL OR p.posted_at >= $2)
              {character_filter}
            GROUP BY h.normalized_hashtag
            ORDER BY publication_count DESC, h.normalized_hashtag
            OFFSET $3
            LIMIT $4
            """,
            channel_id,
            since,
            normalized_page * safe_size,
            safe_size,
        )
    return DashboardPage(
        items=[
            DashboardRankItem(
                key=str(row["normalized_hashtag"]),
                label=f"#{row['hashtag']}",
                count=int(row["publication_count"] or 0),
                secondary_count=int(row["prompt_count"] or 0),
                detail=row["character_name"],
            )
            for row in rows
        ],
        page=normalized_page,
        page_size=safe_size,
        total_items=total,
    )


async def list_character_dashboard(
    database: Database,
    channel_id: int,
    *,
    period: str,
    page: int,
    page_size: int = 8,
) -> DashboardPage:
    since = period_since(period)
    safe_size = max(1, min(page_size, 10))
    safe_page = max(0, page)
    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                """
                SELECT COUNT(DISTINCT h.character_id)
                FROM channel_post_hashtags AS h
                JOIN channel_posts AS p ON p.id = h.post_id
                WHERE p.channel_id = $1
                  AND h.character_id IS NOT NULL
                  AND ($2::TIMESTAMPTZ IS NULL OR p.posted_at >= $2)
                """,
                channel_id,
                since,
            )
            or 0
        )
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            """
            SELECT
                c.id,
                c.name,
                c.category,
                c.universe,
                s.short_label,
                COUNT(DISTINCT p.publication_key) AS publication_count,
                COUNT(DISTINCT p.publication_key) FILTER (WHERE p.is_prompt)
                    AS prompt_count
            FROM channel_post_hashtags AS h
            JOIN channel_posts AS p ON p.id = h.post_id
            JOIN characters AS c ON c.id = h.character_id
            LEFT JOIN character_stories AS s ON s.id = c.story_id
            WHERE p.channel_id = $1
              AND ($2::TIMESTAMPTZ IS NULL OR p.posted_at >= $2)
            GROUP BY c.id, s.id
            ORDER BY publication_count DESC, c.name
            OFFSET $3
            LIMIT $4
            """,
            channel_id,
            since,
            normalized_page * safe_size,
            safe_size,
        )
    return DashboardPage(
        items=[
            DashboardRankItem(
                key=str(row["id"]),
                label=str(row["name"]),
                count=int(row["publication_count"] or 0),
                secondary_count=int(row["prompt_count"] or 0),
                detail=" / ".join(
                    value
                    for value in (
                        row["category"],
                        row["universe"],
                        row["short_label"],
                    )
                    if value
                ) or None,
            )
            for row in rows
        ],
        page=normalized_page,
        page_size=safe_size,
        total_items=total,
    )


async def list_post_type_dashboard(
    database: Database,
    channel_id: int,
    *,
    period: str,
) -> list[DashboardRankItem]:
    since = period_since(period)
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                post_type,
                COUNT(DISTINCT publication_key) AS publication_count,
                ROUND(AVG(post_type_confidence))::INTEGER AS average_confidence
            FROM channel_posts
            WHERE channel_id = $1
              AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
            GROUP BY post_type
            ORDER BY publication_count DESC, post_type
            """,
            channel_id,
            since,
        )
    return [
        DashboardRankItem(
            key=str(row["post_type"]),
            label=str(row["post_type"]),
            count=int(row["publication_count"] or 0),
            secondary_count=int(row["average_confidence"] or 0),
        )
        for row in rows
    ]


async def list_discussion_sources(
    database: Database,
    *,
    parent_channel_id: int,
) -> list[DiscussionSource]:
    async with database._require_pool().acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT chat_id, COALESCE(title, chat_id::TEXT) AS title
            FROM tracked_channels
            WHERE source_kind = 'discussion'
              AND enabled = TRUE
              AND parent_channel_id = $1
            ORDER BY title, chat_id
            """,
            parent_channel_id,
        )
    return [
        DiscussionSource(chat_id=int(row["chat_id"]), title=str(row["title"]))
        for row in rows
    ]


async def get_discussion_dashboard(
    database: Database,
    chat_id: int,
    *,
    period: str,
) -> DiscussionDashboard:
    since = period_since(period)
    async with database._require_pool().acquire() as connection:
        row = await connection.fetchrow(
            """
            SELECT
                COALESCE(MAX(t.title), $1::TEXT) AS title,
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
            WHERE t.chat_id = $1
            GROUP BY t.chat_id
            """,
            chat_id,
            since,
        )
    return DiscussionDashboard(
        chat_id=chat_id,
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


async def list_discussion_participants(
    database: Database,
    chat_id: int,
    *,
    period: str,
    page: int,
    page_size: int = 8,
) -> DashboardPage:
    since = period_since(period)
    safe_size = max(1, min(page_size, 10))
    safe_page = max(0, page)
    async with database._require_pool().acquire() as connection:
        total = int(
            await connection.fetchval(
                """
                SELECT COUNT(DISTINCT sender_id)
                FROM channel_posts
                WHERE channel_id = $1
                  AND sender_id IS NOT NULL
                  AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
                """,
                chat_id,
                since,
            )
            or 0
        )
        total_pages = max(1, (total + safe_size - 1) // safe_size)
        normalized_page = min(safe_page, total_pages - 1)
        rows = await connection.fetch(
            """
            SELECT
                sender_id,
                COALESCE(MAX(sender_name), sender_id) AS sender_name,
                COUNT(*) AS message_count,
                COUNT(*) FILTER (WHERE reply_to_message_id IS NOT NULL)
                    AS reply_count
            FROM channel_posts
            WHERE channel_id = $1
              AND sender_id IS NOT NULL
              AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
            GROUP BY sender_id
            ORDER BY message_count DESC, sender_name
            OFFSET $3
            LIMIT $4
            """,
            chat_id,
            since,
            normalized_page * safe_size,
            safe_size,
        )
    return DashboardPage(
        items=[
            DashboardRankItem(
                key=str(row["sender_id"]),
                label=str(row["sender_name"]),
                count=int(row["message_count"] or 0),
                secondary_count=int(row["reply_count"] or 0),
            )
            for row in rows
        ],
        page=normalized_page,
        page_size=safe_size,
        total_items=total,
    )
