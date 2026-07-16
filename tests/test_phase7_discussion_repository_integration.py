from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime

from velvet_bot.database import Database
from velvet_bot.domains.discussions import (
    DiscussionIngestRepository,
    DiscussionIngestService,
    DiscussionMessageEvent,
    DiscussionRepository,
)

CHANNEL_ID = -1003802812639
DISCUSSION_ID = -1003859952761


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class DiscussionDomainIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database._require_pool().acquire() as connection:
            await connection.execute(
                """
                TRUNCATE
                    discussion_threads,
                    channel_post_hashtags,
                    channel_post_links,
                    channel_posts,
                    tracked_channels,
                    characters
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
            await connection.execute(
                """
                INSERT INTO characters (
                    name, normalized_name, created_by, created_in_chat, universe
                )
                VALUES ('Каэль', 'каэль', 1, 1, 'original')
                """
            )
        self.reports = DiscussionRepository(self.database)
        self.ingest = DiscussionIngestService(
            DiscussionIngestRepository(self.database)
        )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_reactions_and_reports_use_real_schema(self) -> None:
        async with self.database._require_pool().acquire() as connection:
            first_id = await connection.fetchval(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type,
                    sender_id, sender_name, reactions_total
                )
                VALUES (
                    $1::BIGINT, 701, 'live-message:701', NOW(),
                    'Первый #Каэль #Тест', 18, 'photo',
                    'user1', 'Анна', 0
                )
                RETURNING id
                """,
                DISCUSSION_ID,
            )
            await connection.execute(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type,
                    sender_id, sender_name, reply_to_message_id, reactions_total
                )
                VALUES (
                    $1::BIGINT, 702, 'live-message:702', NOW(),
                    'Ответ', 5, 'text',
                    'user1', 'Анна', 701, 0
                )
                """,
                DISCUSSION_ID,
            )
            await connection.execute(
                """
                INSERT INTO channel_post_hashtags (
                    post_id, hashtag, normalized_hashtag, is_character
                )
                VALUES
                    ($1::BIGINT, 'Каэль', 'каэль', TRUE),
                    ($1::BIGINT, 'Тест', 'тест', FALSE)
                """,
                int(first_id),
            )

        self.assertTrue(await self.reports.is_tracked(DISCUSSION_ID))
        self.assertTrue(
            await self.reports.set_reaction_counts(
                discussion_chat_id=DISCUSSION_ID,
                discussion_message_id=701,
                reaction_breakdown={"🔥": 3, "👍": 1},
            )
        )
        self.assertTrue(
            await self.reports.apply_reaction_delta(
                discussion_chat_id=DISCUSSION_ID,
                discussion_message_id=701,
                delta={"🔥": 1, "👍": -1},
            )
        )

        overview = await self.reports.get_overview(DISCUSSION_ID)
        self.assertEqual(2, overview.total_messages)
        self.assertEqual(2, overview.total_publications)
        self.assertEqual(1, overview.unique_participants)
        self.assertEqual(1, overview.reply_messages)
        self.assertEqual(2, overview.total_hashtag_uses)
        self.assertEqual(2, overview.unique_hashtags)
        self.assertEqual(4, overview.total_reactions)

        participants = await self.reports.list_participant_stats(DISCUSSION_ID)
        self.assertEqual(1, len(participants))
        self.assertEqual(2, participants[0].message_count)
        self.assertEqual(2, participants[0].hashtag_count)

        async with self.database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT reactions_total, reaction_breakdown
                FROM channel_posts
                WHERE channel_id = $1::BIGINT AND message_id = 701
                """,
                DISCUSSION_ID,
            )
        self.assertEqual(4, row["reactions_total"])
        self.assertEqual({"🔥": 4}, dict(row["reaction_breakdown"]))

    async def test_live_ingest_links_root_and_reply(self) -> None:
        async with self.database._require_pool().acquire() as connection:
            source_post_id = await connection.fetchval(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type, message_url
                )
                VALUES (
                    $1::BIGINT, 500, 'live-message:500', NOW(),
                    'Пост #Каэль https://t.me/velvet/500', 37, 'photo',
                    'https://t.me/velvet/500'
                )
                RETURNING id
                """,
                CHANNEL_ID,
            )

        root_event = DiscussionMessageEvent(
            chat_id=DISCUSSION_ID,
            chat_title="Velvet discussion",
            chat_username=None,
            message_id=700,
            posted_at=datetime.now(UTC),
            edited_at=None,
            sender_is_bot=False,
            sender_id=f"chat{CHANNEL_ID}",
            sender_name="Velvet Anatomy",
            text_content="Пост #Каэль https://t.me/velvet/500",
            media_group_id=None,
            media_type="photo",
            has_spoiler=False,
            reply_to_message_id=None,
            reply_text="",
            reply_date=None,
            reply_is_automatic_forward=False,
            topic_id=None,
            is_automatic_forward=True,
            forward_channel_id=CHANNEL_ID,
            forward_message_id=500,
        )
        root_result = await self.ingest.ingest(root_event)
        self.assertTrue(root_result.stored)
        self.assertEqual(700, root_result.root_message_id)
        self.assertEqual(500, root_result.source_channel_message_id)

        reply_event = DiscussionMessageEvent(
            chat_id=DISCUSSION_ID,
            chat_title="Velvet discussion",
            chat_username=None,
            message_id=701,
            posted_at=datetime.now(UTC),
            edited_at=None,
            sender_is_bot=False,
            sender_id="user1",
            sender_name="Анна",
            text_content="Комментарий",
            media_group_id=None,
            media_type="text",
            has_spoiler=False,
            reply_to_message_id=700,
            reply_text=root_event.text_content,
            reply_date=root_event.posted_at,
            reply_is_automatic_forward=True,
            topic_id=None,
            is_automatic_forward=False,
            forward_channel_id=None,
            forward_message_id=None,
        )
        reply_result = await self.ingest.ingest(reply_event)
        self.assertTrue(reply_result.stored)
        self.assertEqual(700, reply_result.root_message_id)

        async with self.database._require_pool().acquire() as connection:
            root_row = await connection.fetchrow(
                """
                SELECT discussion_root_message_id, is_discussion_root,
                       source_channel_message_id
                FROM channel_posts
                WHERE channel_id = $1::BIGINT AND message_id = 700
                """,
                DISCUSSION_ID,
            )
            reply_row = await connection.fetchrow(
                """
                SELECT discussion_root_message_id, is_discussion_root
                FROM channel_posts
                WHERE channel_id = $1::BIGINT AND message_id = 701
                """,
                DISCUSSION_ID,
            )
            thread = await connection.fetchrow(
                """
                SELECT channel_message_id, channel_post_id, link_source
                FROM discussion_threads
                WHERE discussion_chat_id = $1::BIGINT AND root_message_id = 700
                """,
                DISCUSSION_ID,
            )
            hashtag = await connection.fetchrow(
                """
                SELECT character_id, is_character
                FROM channel_post_hashtags AS hashtag
                JOIN channel_posts AS post ON post.id = hashtag.post_id
                WHERE post.channel_id = $1::BIGINT
                  AND post.message_id = 700
                  AND hashtag.normalized_hashtag = 'каэль'
                """,
                DISCUSSION_ID,
            )

        self.assertEqual(700, root_row["discussion_root_message_id"])
        self.assertTrue(root_row["is_discussion_root"])
        self.assertEqual(500, root_row["source_channel_message_id"])
        self.assertEqual(700, reply_row["discussion_root_message_id"])
        self.assertFalse(reply_row["is_discussion_root"])
        self.assertEqual(500, thread["channel_message_id"])
        self.assertEqual(int(source_post_id), thread["channel_post_id"])
        self.assertEqual("live_forward", thread["link_source"])
        self.assertTrue(hashtag["is_character"])
        self.assertIsNotNone(hashtag["character_id"])


if __name__ == "__main__":
    unittest.main()
