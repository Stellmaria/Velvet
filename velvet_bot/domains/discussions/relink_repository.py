from __future__ import annotations

from velvet_bot.database import Database
from velvet_bot.domains.discussions.insight_models import RelinkResult


def _affected(status: str) -> int:
    try:
        return int(status.rsplit(" ", 1)[-1])
    except (TypeError, ValueError):
        return 0


class DiscussionRelinkRepository:
    """Rebuild discussion roots and channel-post links in one transaction."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def rebuild(self, discussion_chat_id: int) -> RelinkResult:
        async with self._database._require_pool().acquire() as connection:
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
                          OR post.discussion_root_message_id
                              IS DISTINCT FROM post.message_id
                      )
                    """,
                    int(discussion_chat_id),
                )
                comments_status = await connection.execute(
                    """
                    WITH RECURSIVE reply_tree AS (
                        SELECT
                            channel_id,
                            message_id,
                            message_id AS root_message_id
                        FROM channel_posts
                        WHERE channel_id = $1::BIGINT
                          AND is_discussion_root = TRUE

                        UNION

                        SELECT
                            child.channel_id,
                            child.message_id,
                            parent.root_message_id
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
                      AND target.discussion_root_message_id
                          IS DISTINCT FROM reply_tree.root_message_id
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
        return RelinkResult(
            roots_marked=_affected(roots_status),
            comments_linked=_affected(comments_status),
            threads_linked=_affected(threads_status),
        )


__all__ = ("DiscussionRelinkRepository",)
