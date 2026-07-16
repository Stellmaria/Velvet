from __future__ import annotations

import json
import os
import unittest

from velvet_bot.database import Database
from velvet_bot.media import MediaDescriptor
from velvet_bot.media_set_ai_discovery import discover_media_set_candidates_with_ai
from velvet_bot.media_sets import list_media_set_candidates


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class AIMediaSetsPostgreSQLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database._require_pool().acquire() as connection:
            await connection.execute(
                """
                TRUNCATE
                    media_set_candidate_items,
                    media_set_candidates,
                    media_sets,
                    media_ai_profiles,
                    media_files,
                    characters
                RESTART IDENTITY CASCADE
                """
            )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    @staticmethod
    def descriptor(number: int, file_name: str) -> MediaDescriptor:
        return MediaDescriptor(
            telegram_file_id=f"telegram-ai-{number}",
            telegram_file_unique_id=f"unique-ai-{number}",
            original_file_name=file_name,
            storage_file_name=f"stored-ai-{number}.jpg",
            media_type="photo",
            mime_type="image/jpeg",
            file_size=1024,
        )

    @staticmethod
    def profile(setting: str) -> dict:
        return {
            "series_title_ru": "Дикий Запад",
            "summary_ru": "Сцена американского фронтира.",
            "themes": ["western", "frontier adventure"],
            "genres": ["western"],
            "settings": [setting, "desert"],
            "eras": ["19th century"],
            "environment": ["dusty landscape"],
            "objects": ["cowboy hat", "horse"],
            "wardrobe": ["western clothing"],
            "composition": ["full body"],
            "lighting": ["golden hour"],
            "palette": ["earth tones"],
            "mood": ["adventurous"],
            "actions": ["standing"],
            "series_keywords": ["western", "cowboy", "frontier"],
            "people_count": 1,
            "confidence": 94,
        }

    async def test_ai_groups_different_characters_without_filename_match(self) -> None:
        ada, _ = await self.database.create_character(
            "Ада",
            created_by=1,
            created_in_chat=1,
        )
        eric, _ = await self.database.create_character(
            "Эрик",
            created_by=1,
            created_in_chat=1,
        )
        first = await self.database.save_character_media(
            ada,
            self.descriptor(1, "completely-unrelated-a.jpg"),
            saved_by=1,
            saved_in_chat=1,
            source_chat_id=1,
            source_message_id=101,
            source_thread_id=None,
            command_message_id=201,
        )
        second = await self.database.save_character_media(
            eric,
            self.descriptor(2, "another-random-name.jpg"),
            saved_by=1,
            saved_in_chat=1,
            source_chat_id=1,
            source_message_id=102,
            source_thread_id=None,
            command_message_id=202,
        )

        async with self.database._require_pool().acquire() as connection:
            await connection.executemany(
                """
                INSERT INTO media_ai_profiles (
                    media_id, status, provider, model, analysis,
                    semantic_text, analyzed_at
                )
                VALUES ($1::BIGINT, 'ready', 'ollama', 'qwen3-vl:8b',
                        $2::JSONB, 'western semantic profile', NOW())
                """,
                [
                    (first.media_id, json.dumps(self.profile("saloon"))),
                    (second.media_id, json.dumps(self.profile("ranch"))),
                ],
            )

        created = await discover_media_set_candidates_with_ai(self.database)
        page = await list_media_set_candidates(self.database, status="pending")

        self.assertGreaterEqual(created, 1)
        ai_candidates = [
            candidate
            for candidate in page.items
            if candidate.suggested_title == "Дикий Запад"
        ]
        self.assertEqual(1, len(ai_candidates))
        self.assertEqual(
            {first.media_id, second.media_id},
            {item.media_id for item in ai_candidates[0].items},
        )
        self.assertGreaterEqual(ai_candidates[0].score, 70)

        async with self.database._require_pool().acquire() as connection:
            key = await connection.fetchval(
                """
                SELECT candidate_key
                FROM media_set_candidates
                WHERE id = $1::BIGINT
                """,
                ai_candidates[0].id,
            )
        self.assertTrue(str(key).startswith("ai:"))


if __name__ == "__main__":
    unittest.main()
