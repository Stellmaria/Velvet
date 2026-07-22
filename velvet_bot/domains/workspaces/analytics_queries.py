from __future__ import annotations

from velvet_bot.analytics_dashboard import DashboardPage, DashboardRankItem, period_since
from velvet_bot.channel_analytics import CharacterUsageStat
from velvet_bot.database import Database


async def list_workspace_character_usage_stats(
    database: Database,
    channel_id: int,
    *,
    workspace_id: int,
    limit: int = 20,
) -> list[CharacterUsageStat]:
    async with database.acquire() as connection:
        rows = await connection.fetch(
            """
            SELECT
                c.id AS character_id,
                c.name,
                c.category,
                c.universe,
                story.short_label AS story_short_label,
                story.title AS story_title,
                COUNT(DISTINCT post.publication_key) AS publication_count,
                COUNT(DISTINCT post.publication_key) FILTER (WHERE post.is_prompt)
                    AS prompt_count,
                MAX(post.posted_at) AS last_used_at
            FROM channel_post_hashtags AS hashtag
            JOIN channel_posts AS post ON post.id = hashtag.post_id
            JOIN characters AS c ON c.id = hashtag.character_id
            LEFT JOIN workspace_character_story_links AS primary_link
              ON primary_link.workspace_id = c.workspace_id
             AND primary_link.character_id = c.id
             AND primary_link.is_primary
            LEFT JOIN workspace_stories AS story
              ON story.workspace_id = primary_link.workspace_id
             AND story.id = primary_link.story_id
            WHERE post.channel_id = $1::BIGINT
              AND c.workspace_id = $2::BIGINT
            GROUP BY c.id, story.id
            ORDER BY publication_count DESC, last_used_at DESC, c.name
            LIMIT $3::INTEGER
            """,
            int(channel_id),
            int(workspace_id),
            max(1, min(int(limit), 100)),
        )
    return [
        CharacterUsageStat(
            character_id=int(row["character_id"]),
            name=str(row["name"]),
            publication_count=int(row["publication_count"] or 0),
            prompt_count=int(row["prompt_count"] or 0),
            last_used_at=row["last_used_at"],
            category=row["category"],
            universe=row["universe"],
            story_short_label=row["story_short_label"],
            story_title=row["story_title"],
        )
        for row in rows
    ]


async def list_workspace_character_dashboard(
    database: Database,
    channel_id: int,
    *,
    workspace_id: int,
    period: str,
    page: int,
    page_size: int = 8,
) -> DashboardPage:
    since = period_since(period)
    safe_size = max(1, min(int(page_size), 10))
    safe_page = max(0, int(page))
    async with database.acquire() as connection:
        total = int(
            await connection.fetchval(
                """
                SELECT COUNT(DISTINCT hashtag.character_id)
                FROM channel_post_hashtags AS hashtag
                JOIN channel_posts AS post ON post.id = hashtag.post_id
                JOIN characters AS c ON c.id = hashtag.character_id
                WHERE post.channel_id = $1::BIGINT
                  AND c.workspace_id = $2::BIGINT
                  AND ($3::TIMESTAMPTZ IS NULL OR post.posted_at >= $3)
                """,
                int(channel_id),
                int(workspace_id),
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
                story.short_label,
                COUNT(DISTINCT post.publication_key) AS publication_count,
                COUNT(DISTINCT post.publication_key) FILTER (WHERE post.is_prompt)
                    AS prompt_count
            FROM channel_post_hashtags AS hashtag
            JOIN channel_posts AS post ON post.id = hashtag.post_id
            JOIN characters AS c ON c.id = hashtag.character_id
            LEFT JOIN workspace_character_story_links AS primary_link
              ON primary_link.workspace_id = c.workspace_id
             AND primary_link.character_id = c.id
             AND primary_link.is_primary
            LEFT JOIN workspace_stories AS story
              ON story.workspace_id = primary_link.workspace_id
             AND story.id = primary_link.story_id
            WHERE post.channel_id = $1::BIGINT
              AND c.workspace_id = $2::BIGINT
              AND ($3::TIMESTAMPTZ IS NULL OR post.posted_at >= $3)
            GROUP BY c.id, story.id
            ORDER BY publication_count DESC, c.name
            OFFSET $4::INTEGER
            LIMIT $5::INTEGER
            """,
            int(channel_id),
            int(workspace_id),
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
                    str(value)
                    for value in (
                        row["category"],
                        row["universe"],
                        row["short_label"],
                    )
                    if value
                )
                or None,
            )
            for row in rows
        ],
        page=normalized_page,
        page_size=safe_size,
        total_items=total,
    )


__all__ = (
    "list_workspace_character_dashboard",
    "list_workspace_character_usage_stats",
)
