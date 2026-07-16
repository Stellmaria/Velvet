from __future__ import annotations

import os
import unittest

from velvet_bot.database import Database
from velvet_bot.discussion_relink import rebuild_discussion_threads

CHANNEL_ID = -1003802812639
DISCUSSION_ID = -1003859952761


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class DiscussionRelinkIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database._require_pool().acquire() as connection:
            await connection.execute(
                """
                TRUNCATE discussion_threads, channel_posts, tracked_channels
                RESTART IDENTITY CASCADE
                """
            )
            await connection.execute(
                """
                INSERT INTO tracked_channels (
                    chat_id, title, source_kind, parent_channel_id, enabled
                )
                VALUES
                    ($1::BIGINT, 'Velvet Anatomy', 'channel', NULL, TRUE),
                    ($2::BIGINT, 'Velvet discussion', 'discussion', $1::BIGINT, TRUE)
                """,
                CHANNEL_ID,
                DISCUSSION_ID,
            )
            source_id = await connection.fetchval(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type
                )
                VALUES (
                    $1::BIGINT, 500, 'live-message:500',
                    NOW() - INTERVAL '1 hour',
                    'Одинаковый текст поста', 21, 'photo'
                )
                RETURNING id
                """,
                CHANNEL_ID,
            )
            self.source_id = int(source_id)
            await connection.execute(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type,
                    sender_id, sender_name,
                    is_discussion_root, discussion_root_message_id
                )
                VALUES (
                    $1::BIGINT, 700, 'live-message:700',
                    NOW() - INTERVAL '59 minutes',
                    'Одинаковый текст поста', 21, 'photo',
                    'channel-root', 'Velvet Anatomy', FALSE, NULL
                )
                """,
                DISCUSSION_ID,
            )
            await connection.execute(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type,
                    sender_id, sender_name, reply_to_message_id,
                    is_discussion_root, discussion_root_message_id
                )
                VALUES
                    ($1::BIGINT, 701, 'live-message:701',
                     NOW() - INTERVAL '58 minutes',
                     'Первый ответ', 12, 'text',
                     'anna', 'Анна', 700, FALSE, NULL),
                    ($1::BIGINT, 702, 'live-message:702',
                     NOW() - INTERVAL '57 minutes',
                     'Вложенный ответ', 15, 'text',
                     'maria', 'Мария', 701, FALSE, NULL)
                """,
                DISCUSSION_ID,
            )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_rebuild_marks_root_comments_and_thread(self) -> None:
        result = await rebuild_discussion_threads(
            self.database,
            DISCUSSION_ID,
        )
        self.assertEqual(1, result.roots_marked)
        self.assertEqual(2, result.comments_linked)
        self.assertEqual(1, result.threads_linked)

        async with self.database._require_pool().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT message_id, is_discussion_root,
                       discussion_root_message_id
                FROM channel_posts
                WHERE channel_id = $1::BIGINT
                ORDER BY message_id
                """,
                DISCUSSION_ID,
            )
            thread = await connection.fetchrow(
                """
                SELECT parent_channel_id, channel_message_id,
                       channel_post_id, link_source
                FROM discussion_threads
                WHERE discussion_chat_id = $1::BIGINT
                  AND root_message_id = 700
                """,
                DISCUSSION_ID,
            )
        values = {
            int(row["message_id"]): (
                bool(row["is_discussion_root"]),
                int(row["discussion_root_message_id"]),
            )
            for row in rows
        }
        self.assertEqual((True, 700), values[700])
        self.assertEqual((False, 700), values[701])
        self.assertEqual((False, 700), values[702])
        self.assertEqual(CHANNEL_ID, thread["parent_channel_id"])
        self.assertEqual(500, thread["channel_message_id"])
        self.assertEqual(self.source_id, thread["channel_post_id"])
        self.assertEqual("rebuild_exact_text", thread["link_source"])


if __name__ == "__main__":
    unittest.main()
