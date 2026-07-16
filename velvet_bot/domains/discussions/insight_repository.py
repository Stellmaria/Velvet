from __future__ import annotations

from datetime import datetime

from velvet_bot.database import Database
from velvet_bot.domains.discussions.insight_models import DiscussionSummary


class DiscussionInsightRepository:
    """PostgreSQL queries for detailed discussion analytics."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def get_summary(
        self,
        *,
        discussion_chat_id: int,
        parent_channel_id: int,
        since: datetime | None,
    ) -> DiscussionSummary:
        async with self._database._require_pool().acquire() as connection:
            comment_row = await connection.fetchrow(
                """
                WITH linked_comments AS (
                    SELECT
                        comment.id,
                        comment.sender_id,
                        comment.reactions_total,
                        comment.posted_at,
                        source.publication_key AS source_publication_key
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
                    COUNT(DISTINCT source_publication_key) AS linked_threads,
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
                    COUNT(*) FILTER (WHERE COALESCE(counts.comment_count, 0) = 0)
                        AS without_comments,
                    COALESCE(AVG(COALESCE(counts.comment_count, 0)), 0)
                        AS average_comments
                FROM publications AS publication
                LEFT JOIN comment_counts AS counts USING (publication_key)
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


__all__ = ("DiscussionInsightRepository",)
