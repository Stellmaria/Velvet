from __future__ import annotations

import os
import unittest

from velvet_bot.database import Database
from velvet_bot.discussion_activity import (
    get_activity_breakdown,
    list_activity_spikes,
    list_publications_without_comments,
)

CHANNEL_ID = -1003802812639
DISCUSSION_ID = -1003859952761


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class DiscussionActivityIntegrationTests(unittest.IsolatedAsyncioTestCase):
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
            discussed_id = await connection.fetchval(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type
                )
                VALUES (
                    $1::BIGINT, 500, 'live-message:500',
                    NOW() - INTERVAL '7 days',
                    'Обсуждаемая публикация', 22, 'photo'
                )
                RETURNING id
                """,
                CHANNEL_ID,
            )
            await connection.execute(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type
                )
                VALUES (
                    $1::BIGINT, 501, 'live-message:501',
                    NOW() - INTERVAL '6 days',
                    'Тихая публикация', 16, 'photo'
                )
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
                )
                VALUES (
                    $1::BIGINT, 700, 'live-message:700',
                    NOW() - INTERVAL '7 days' + INTERVAL '1 minute',
                    'Обсуждаемая публикация', 22, 'photo',
                    'channel-root', 'Velvet Anatomy', 700, TRUE, 500
                )
                """,
                DISCUSSION_ID,
            )
            await connection.execute(
                """
                INSERT INTO discussion_threads (
                    discussion_chat_id, root_message_id,
                    parent_channel_id, channel_message_id,
                    channel_post_id, link_source
                )
                VALUES ($1::BIGINT, 700, $2::BIGINT,
                        500, $3::BIGINT, 'test')
                """,
                DISCUSSION_ID,
                CHANNEL_ID,
                int(discussed_id),
            )

            message_id = 800
            for days_ago in range(6, 1, -1):
                await connection.execute(
                    """
                    INSERT INTO channel_posts (
                        channel_id, message_id, publication_key, posted_at,
                        text_content, text_length, media_type,
                        sender_id, sender_name, reply_to_message_id,
                        discussion_root_message_id, is_discussion_root
                    )
                    VALUES (
                        $1::BIGINT, $2::BIGINT, $3::TEXT,
                        NOW() - ($4::INTEGER * INTERVAL '1 day'),
                        'Обычный комментарий', 19, 'text',
                        'user-normal', 'Участник', 700, 700, FALSE
                    )
                    """,
                    DISCUSSION_ID,
                    message_id,
                    f"live-message:{message_id}",
                    days_ago,
                )
                message_id += 1

            for index in range(20):
                await connection.execute(
                    """
                    INSERT INTO channel_posts (
                        channel_id, message_id, publication_key, posted_at,
                        text_content, text_length, media_type,
                        sender_id, sender_name, reply_to_message_id,
                        discussion_root_message_id, is_discussion_root
                    )
                    VALUES (
                        $1::BIGINT, $2::BIGINT, $3::TEXT,
                        timezone(
                            'Europe/Berlin',
                            date_trunc(
                                'day',
                                timezone('Europe/Berlin', NOW())
                            )
                            - INTERVAL '1 day'
                            + INTERVAL '12 hours'
                            + ($4::INTEGER * INTERVAL '1 minute')
                        ),
                        'Комментарий всплеска', 19, 'text',
                        'user-spike', 'Активный участник', 700, 700, FALSE
                    )
                    """,
                    DISCUSSION_ID,
                    message_id,
                    f"live-message:{message_id}",
                    index,
                )
                message_id += 1

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_silent_publications_and_activity_use_domain_service(self) -> None:
        silent = await list_publications_without_comments(
            self.database,
            DISCUSSION_ID,
            CHANNEL_ID,
            period="30d",
            page=0,
        )
        self.assertEqual(1, silent.total_items)
        self.assertEqual("Тихая публикация", silent.items[0].label)
        self.assertEqual("0", str(silent.items[0].count))

        breakdown = await get_activity_breakdown(
            self.database,
            DISCUSSION_ID,
            period="30d",
            timezone_name="Europe/Berlin",
        )
        self.assertEqual(25, sum(breakdown.weekdays))
        self.assertEqual(25, sum(breakdown.hours))
        self.assertEqual(7, len(breakdown.weekdays))
        self.assertEqual(24, len(breakdown.hours))

        spikes = await list_activity_spikes(
            self.database,
            DISCUSSION_ID,
            period="30d",
            timezone_name="Europe/Berlin",
        )
        self.assertEqual(1, len(spikes))
        self.assertEqual(20, spikes[0].comment_count)
        self.assertGreater(spikes[0].ratio, 4.0)


if __name__ == "__main__":
    unittest.main()
