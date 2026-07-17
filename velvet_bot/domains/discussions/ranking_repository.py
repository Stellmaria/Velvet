from __future__ import annotations

from datetime import datetime

from velvet_bot.analytics_dashboard import DashboardPage, DashboardRankItem
from velvet_bot.database import Database


def _safe_page(page: int, page_size: int, total: int) -> tuple[int, int]:
    safe_size = max(1, min(int(page_size), 10))
    total_pages = max(1, (total + safe_size - 1) // safe_size)
    return min(max(0, int(page)), total_pages - 1), safe_size


class DiscussionRankingRepository:
    """PostgreSQL rankings for discussion participants and publication metadata."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def _rank_page(
        self,
        count_sql: str,
        rows_sql: str,
        args: tuple[object, ...],
        *,
        page: int,
        page_size: int = 8,
    ) -> DashboardPage:
        async with self._database.acquire() as connection:
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
        self,
        *,
        discussion_chat_id: int,
        since: datetime | None,
        page: int,
    ) -> DashboardPage:
        where = """
            channel_id = $1::BIGINT
            AND is_discussion_root = FALSE
            AND discussion_root_message_id IS NOT NULL
            AND sender_id IS NOT NULL
            AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
        """
        return await self._rank_page(
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
        self,
        *,
        discussion_chat_id: int,
        since: datetime | None,
        page: int,
    ) -> DashboardPage:
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
                COUNT(DISTINCT child.sender_id) FILTER (
                    WHERE child.sender_id IS NOT NULL
                ) AS secondary_count,
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
        return await self._rank_page(
            count_sql,
            rows_sql,
            (int(discussion_chat_id), since),
            page=page,
        )

    async def list_reaction_leaders(
        self,
        *,
        discussion_chat_id: int,
        since: datetime | None,
        page: int,
    ) -> DashboardPage:
        where = """
            channel_id = $1::BIGINT
            AND is_discussion_root = FALSE
            AND discussion_root_message_id IS NOT NULL
            AND sender_id IS NOT NULL
            AND reactions_total > 0
            AND ($2::TIMESTAMPTZ IS NULL OR posted_at >= $2)
        """
        return await self._rank_page(
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
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        since: datetime | None,
        page: int,
    ) -> DashboardPage:
        base = """
            WITH publication_characters AS (
                SELECT DISTINCT
                    source.publication_key,
                    character.id,
                    character.name,
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
        return await self._rank_page(
            base + """
                SELECT COUNT(DISTINCT character.id)
                FROM publication_characters AS character
                JOIN comment_publications AS comment USING (publication_key)
            """,
            base + """
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
            """,
            (int(discussion_chat_id), int(parent_channel_id), since),
            page=page,
        )

    async def list_discussed_universes(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        since: datetime | None,
        page: int,
    ) -> DashboardPage:
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
        return await self._rank_page(
            base + "SELECT COUNT(DISTINCT universe) FROM publication_universes",
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
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        since: datetime | None,
        page: int,
    ) -> DashboardPage:
        base = """
            WITH character_story_map AS (
                SELECT character_id, story_id FROM character_story_links
                UNION
                SELECT id AS character_id, story_id
                FROM characters
                WHERE story_id IS NOT NULL
            ),
            publication_stories AS (
                SELECT DISTINCT
                    source.publication_key,
                    story.id,
                    story.short_label,
                    story.title,
                    story.universe
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
        return await self._rank_page(
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


__all__ = ("DiscussionRankingRepository",)
