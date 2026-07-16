from __future__ import annotations

import os
import unittest

from velvet_bot.database import Database
from velvet_bot.discussion_rankings import (
    list_active_participants,
    list_discussed_characters,
    list_discussed_stories,
    list_discussed_universes,
    list_most_replied_participants,
    list_reaction_leaders,
)

CHANNEL_ID = -1003802812639
DISCUSSION_ID = -1003859952761


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class DiscussionRankingsIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database._require_pool().acquire() as connection:
            await connection.execute(
                """
                TRUNCATE
                    discussion_threads,
                    channel_post_hashtags,
                    channel_posts,
                    tracked_channels,
                    character_story_links,
                    character_stories,
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
            story_id = await connection.fetchval(
                """
                INSERT INTO character_stories (
                    universe, key, short_label, title,
                    sort_order, release_order, release_precision
                )
                VALUES ('original', 'ranking-story', 'RS',
                        'Ranking story', 10, 10, 'unknown')
                RETURNING id
                """
            )
            character_id = await connection.fetchval(
                """
                INSERT INTO characters (
                    name, normalized_name, created_by, created_in_chat,
                    universe, story_id
                )
                VALUES ('Каэль', 'каэль', 1, 1, 'original', $1::BIGINT)
                RETURNING id
                """,
                int(story_id),
            )
            source_post_id = await connection.fetchval(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type
                )
                VALUES (
                    $1::BIGINT, 500, 'live-message:500',
                    NOW() - INTERVAL '1 hour',
                    'Пост #Каэль', 11, 'photo'
                )
                RETURNING id
                """,
                CHANNEL_ID,
            )
            await connection.execute(
                """
                INSERT INTO channel_post_hashtags (
                    post_id, hashtag, normalized_hashtag,
                    character_id, is_character
                )
                VALUES ($1::BIGINT, 'Каэль', 'каэль', $2::BIGINT, TRUE)
                """,
                int(source_post_id),
                int(character_id),
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
                    NOW() - INTERVAL '59 minutes',
                    'Пост #Каэль', 11, 'photo',
                    'channel-root', 'Velvet Anatomy', 700, TRUE, 500
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
                )
                VALUES
                    ($1::BIGINT, 701, 'live-message:701',
                     NOW() - INTERVAL '58 minutes',
                     'Комментарий Анны', 16, 'text',
                     'anna', 'Анна', 700, 4, 700, FALSE),
                    ($1::BIGINT, 702, 'live-message:702',
                     NOW() - INTERVAL '57 minutes',
                     'Ответ Марии', 12, 'text',
                     'maria', 'Мария', 701, 2, 700, FALSE),
                    ($1::BIGINT, 703, 'live-message:703',
                     NOW() - INTERVAL '56 minutes',
                     'Ответ Анны', 11, 'text',
                     'anna', 'Анна', 702, 1, 700, FALSE)
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
                int(source_post_id),
            )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_all_rankings_use_domain_repository(self) -> None:
        active = await list_active_participants(
            self.database,
            DISCUSSION_ID,
            period="30d",
            page=0,
        )
        self.assertEqual(2, active.total_items)
        self.assertEqual(("Анна", 2), (active.items[0].label, active.items[0].count))
        self.assertEqual(("Мария", 1), (active.items[1].label, active.items[1].count))

        replied = await list_most_replied_participants(
            self.database,
            DISCUSSION_ID,
            period="30d",
            page=0,
        )
        self.assertEqual(2, replied.total_items)
        replied_counts = {item.label: item.count for item in replied.items}
        self.assertEqual({"Анна": 1, "Мария": 1}, replied_counts)

        reactions = await list_reaction_leaders(
            self.database,
            DISCUSSION_ID,
            period="30d",
            page=0,
        )
        self.assertEqual(("Анна", 5), (
            reactions.items[0].label,
            reactions.items[0].count,
        ))
        self.assertEqual(("Мария", 2), (
            reactions.items[1].label,
            reactions.items[1].count,
        ))

        characters = await list_discussed_characters(
            self.database,
            DISCUSSION_ID,
            CHANNEL_ID,
            period="30d",
            page=0,
        )
        self.assertEqual(1, characters.total_items)
        self.assertEqual("Каэль", characters.items[0].label)
        self.assertEqual(3, characters.items[0].count)
        self.assertEqual(1, characters.items[0].secondary_count)
        self.assertEqual("original", characters.items[0].detail)

        universes = await list_discussed_universes(
            self.database,
            DISCUSSION_ID,
            CHANNEL_ID,
            period="30d",
            page=0,
        )
        self.assertEqual(1, universes.total_items)
        self.assertEqual("original", universes.items[0].key)
        self.assertEqual(3, universes.items[0].count)

        stories = await list_discussed_stories(
            self.database,
            DISCUSSION_ID,
            CHANNEL_ID,
            period="30d",
            page=0,
        )
        self.assertEqual(1, stories.total_items)
        self.assertEqual("RS", stories.items[0].label)
        self.assertEqual(3, stories.items[0].count)
        self.assertIn("Ranking story", stories.items[0].detail or "")


if __name__ == "__main__":
    unittest.main()
