from __future__ import annotations

import os
import unittest

from velvet_bot.database import Database
from velvet_bot.discussion_post_insights import (
    get_discussed_post,
    list_discussed_posts,
)

CHANNEL_ID = -1003802812639
DISCUSSION_ID = -1003859952761


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class DiscussedPostsIntegrationTests(unittest.IsolatedAsyncioTestCase):
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
                ) VALUES
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
                    text_content, text_length, media_type,
                    view_count, reactions_total, message_url
                ) VALUES (
                    $1::BIGINT, 500, 'live-message:500', NOW() - INTERVAL '1 hour',
                    'Пост #Каэль', 11, 'photo', 1240, 83,
                    'https://t.me/velvet/500'
                ) RETURNING id
                """,
                CHANNEL_ID,
            )
            await connection.execute(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type,
                    sender_id, sender_name, discussion_root_message_id,
                    is_discussion_root, source_channel_message_id
                ) VALUES (
                    $1::BIGINT, 700, 'live-message:700', NOW() - INTERVAL '59 minutes',
                    'Пост #Каэль', 11, 'photo',
                    'chat-archive', 'Velvet Anatomy', 700, TRUE, 500
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
                    reactions_total, discussion_root_message_id,
                    is_discussion_root
                ) VALUES
                    ($1::BIGINT, 701, 'live-message:701',
                     NOW() - INTERVAL '58 minutes',
                     'Первый комментарий', 19, 'text',
                     'user1', 'Анна', 700, 4, 700, FALSE),
                    ($1::BIGINT, 702, 'live-message:702',
                     NOW() - INTERVAL '55 minutes',
                     'Ответ', 5, 'text',
                     'user2', 'Мария', 701, 2, 700, FALSE)
                """,
                DISCUSSION_ID,
            )
            await connection.execute(
                """
                INSERT INTO discussion_threads (
                    discussion_chat_id, root_message_id,
                    parent_channel_id, channel_message_id,
                    channel_post_id, link_source
                ) VALUES ($1::BIGINT, 700, $2::BIGINT, 500, $3::BIGINT, 'test')
                """,
                DISCUSSION_ID,
                CHANNEL_ID,
                int(source_id),
            )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_page_and_detail_use_domain_repository(self) -> None:
        page = await list_discussed_posts(
            self.database,
            DISCUSSION_ID,
            CHANNEL_ID,
            period="30d",
            page=0,
        )
        self.assertEqual(1, page.total_items)
        self.assertEqual(2, page.items[0].comment_count)
        self.assertEqual(1240, page.items[0].view_count)
        self.assertEqual(83, page.items[0].channel_reactions)
        self.assertEqual(2, page.items[0].unique_participants)
        self.assertEqual(6, page.items[0].comment_reactions)

        detail = await get_discussed_post(
            self.database,
            DISCUSSION_ID,
            CHANNEL_ID,
            page.items[0].post_id,
            period="30d",
        )
        self.assertIsNotNone(detail)
        self.assertEqual(page.items[0].publication_key, detail.publication_key)
        self.assertEqual(2, detail.comment_count)
        self.assertEqual(6, detail.comment_reactions)


if __name__ == "__main__":
    unittest.main()
