from __future__ import annotations

from datetime import datetime

from velvet_bot.database import Database
from velvet_bot.domains.discussions.insight_models import (
    DiscussedPost,
    DiscussedPostPage,
)


def _safe_page(page: int, page_size: int, total: int) -> tuple[int, int]:
    safe_size = max(1, min(int(page_size), 10))
    total_pages = max(1, (total + safe_size - 1) // safe_size)
    return min(max(0, int(page)), total_pages - 1), safe_size


class DiscussionPostInsightRepository:
    """PostgreSQL queries for discussed publications and post detail."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_posts(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        since: datetime | None,
        page: int,
        page_size: int = 6,
    ) -> DiscussedPostPage:
        async with self._database._require_pool().acquire() as connection:
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
                        COALESCE(SUM(comment.reactions_total), 0)
                            AS comment_reactions
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
            items=[self._row_to_post(row) for row in rows],
            page=normalized_page,
            page_size=safe_size,
            total_items=total,
        )

    async def get_post(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        post_id: int,
        since: datetime | None,
    ) -> DiscussedPost | None:
        async with self._database._require_pool().acquire() as connection:
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
                      AND source.publication_key = (
                          SELECT publication_key FROM selected
                      )
                ),
                comments AS (
                    SELECT
                        COUNT(*) AS comment_count,
                        MIN(posted_at) AS first_comment_at,
                        COUNT(DISTINCT sender_id) FILTER (
                            WHERE sender_id IS NOT NULL
                        ) AS unique_participants,
                        COALESCE(SUM(reactions_total), 0) AS comment_reactions
                    FROM channel_posts
                    WHERE channel_id = $1::BIGINT
                      AND is_discussion_root = FALSE
                      AND discussion_root_message_id IN (
                          SELECT root_message_id FROM roots
                      )
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
        return self._row_to_post(row) if row is not None else None

    @staticmethod
    def _row_to_post(row) -> DiscussedPost:
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


__all__ = ("DiscussionPostInsightRepository",)
