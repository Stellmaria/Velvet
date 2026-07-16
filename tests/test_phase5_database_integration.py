import os
import unittest

from velvet_bot.database import Database
from velvet_bot.discussion_insights import (
    get_discussion_summary,
    list_active_participants,
    list_discussed_characters,
    list_discussed_posts,
)


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PhaseFivePostgreSQLTests(unittest.IsolatedAsyncioTestCase):
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
                    (-1003802812639, 'Velvet Anatomy', 'channel', NULL, TRUE),
                    (-1003859952761, 'Velvet discussion', 'discussion',
                     -1003802812639, TRUE)
                """
            )

            character_id = await connection.fetchval(
                """
                INSERT INTO characters (
                    name, normalized_name, created_by, created_in_chat,
                    universe
                )
                VALUES ('Каэль', 'каэль', 1, 1, 'Original')
                RETURNING id
                """
            )
            source_post_id = await connection.fetchval(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type, view_count,
                    reactions_total, message_url
                )
                VALUES (
                    -1003802812639, 500, 'live-message:500',
                    NOW() - INTERVAL '1 hour',
                    'Пост #Kael', 10, 'photo', 1240, 83,
                    'https://t.me/velvetAnatomy/500'
                )
                RETURNING id
                """
            )
            await connection.execute(
                """
                INSERT INTO channel_post_hashtags (
                    post_id, hashtag, normalized_hashtag,
                    character_id, is_character
                )
                VALUES ($1, 'Kael', 'kael', $2, TRUE)
                """,
                source_post_id,
                character_id,
            )
            await connection.execute(
                """
                INSERT INTO channel_posts (
                    channel_id, message_id, publication_key, posted_at,
                    text_content, text_length, media_type,
                    sender_id, sender_name, reactions_total,
                    discussion_root_message_id, is_discussion_root,
                    source_channel_message_id
                )
                VALUES (
                    -1003859952761, 700, 'live-message:700',
                    NOW() - INTERVAL '59 minutes',
                    'Пост #Kael', 10, 'photo',
                    'chat-1003802812639', 'Velvet Anatomy', 0,
                    700, TRUE, 500
                )
                """
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
                    (-1003859952761, 701, 'live-message:701',
                     NOW() - INTERVAL '58 minutes',
                     'Первый комментарий', 19, 'text',
                     'user1', 'Анна', 700, 4, 700, FALSE),
                    (-1003859952761, 702, 'live-message:702',
                     NOW() - INTERVAL '55 minutes',
                     'Ответ', 5, 'text',
                     'user2', 'Мария', 701, 2, 700, FALSE)
                """
            )
            await connection.execute(
                """
                INSERT INTO discussion_threads (
                    discussion_chat_id, root_message_id,
                    parent_channel_id, channel_message_id,
                    channel_post_id, link_source
                )
                VALUES (-1003859952761, 700, -1003802812639,
                        500, $1, 'test')
                """,
                source_post_id,
            )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    async def test_summary_and_publication_metrics(self) -> None:
        summary = await get_discussion_summary(
            self.database,
            -1003859952761,
            -1003802812639,
            period="30d",
        )
        self.assertEqual(2, summary.total_comments)
        self.assertEqual(2, summary.unique_participants)
        self.assertEqual(6, summary.total_comment_reactions)
        self.assertEqual(1, summary.linked_threads)
        self.assertEqual(2.0, summary.average_comments_per_publication)

        page = await list_discussed_posts(
            self.database,
            -1003859952761,
            -1003802812639,
            period="30d",
            page=0,
        )
        self.assertEqual(1, page.total_items)
        self.assertEqual(2, page.items[0].comment_count)
        self.assertEqual(1240, page.items[0].view_count)
        self.assertEqual(83, page.items[0].channel_reactions)
        self.assertEqual(2, page.items[0].unique_participants)
        self.assertEqual(6, page.items[0].comment_reactions)
        self.assertGreaterEqual(page.items[0].first_comment_seconds or 0, 60)

    async def test_participant_and_character_rankings(self) -> None:
        participants = await list_active_participants(
            self.database,
            -1003859952761,
            period="30d",
            page=0,
        )
        self.assertEqual(2, participants.total_items)
        self.assertEqual("Анна", participants.items[0].label)

        characters = await list_discussed_characters(
            self.database,
            -1003859952761,
            -1003802812639,
            period="30d",
            page=0,
        )
        self.assertEqual(1, characters.total_items)
        self.assertEqual("Каэль", characters.items[0].label)
        self.assertEqual(2, characters.items[0].count)


if __name__ == "__main__":
    unittest.main()
