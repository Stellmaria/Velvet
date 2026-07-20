from __future__ import annotations

import os
import unittest

from velvet_bot.database import Database
from velvet_bot.media import MediaDescriptor
from velvet_bot.media_set_actions import create_media_set
from velvet_bot.media_set_candidate_listing import list_media_set_candidates_by_size
from velvet_bot.media_set_duplicate_actions import create_set_candidate_from_duplicate


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class MediaSetExclusivityPostgreSQLTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        async with self.database.acquire() as connection:
            await connection.execute(
                """
                TRUNCATE
                    media_duplicate_candidates,
                    media_set_candidate_items,
                    media_set_candidates,
                    media_sets,
                    media_files,
                    characters
                RESTART IDENTITY CASCADE
                """
            )

    async def asyncTearDown(self) -> None:
        await self.database.close()

    @staticmethod
    def descriptor(number: int) -> MediaDescriptor:
        return MediaDescriptor(
            telegram_file_id=f"set-policy-file-{number}",
            telegram_file_unique_id=f"set-policy-unique-{number}",
            original_file_name=f"set-policy-{number}.jpg",
            storage_file_name=f"set-policy-{number}__{number:024x}.jpg",
            media_type="photo",
            mime_type="image/jpeg",
            file_size=1024,
        )

    async def create_media(self, number: int) -> int:
        character, _ = await self.database.create_character(
            f"Персонаж {number}",
            created_by=1,
            created_in_chat=1,
        )
        saved = await self.database.save_character_media(
            character,
            self.descriptor(number),
            saved_by=1,
            saved_in_chat=1,
            source_chat_id=1,
            source_message_id=100 + number,
            source_thread_id=None,
            command_message_id=200 + number,
        )
        return saved.media_id

    async def insert_candidate(
        self,
        *,
        key: str,
        score: int,
        media_ids: tuple[int, ...],
    ) -> int:
        async with self.database.acquire() as connection:
            candidate_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO media_set_candidates (
                        candidate_key, suggested_title, reason, score
                    )
                    VALUES ($1::TEXT, $2::VARCHAR, 'Тестовое предложение', $3::SMALLINT)
                    RETURNING id
                    """,
                    key,
                    key,
                    score,
                )
            )
            await connection.executemany(
                """
                INSERT INTO media_set_candidate_items (
                    candidate_id, media_id, selected, context_score, reason
                )
                VALUES ($1::BIGINT, $2::BIGINT, TRUE, $3::SMALLINT, 'Тест')
                """,
                [(candidate_id, media_id, score) for media_id in media_ids],
            )
        return candidate_id

    async def test_count_first_ranking_and_accepted_set_cleanup(self) -> None:
        media_ids = tuple([await self.create_media(index) for index in range(1, 6)])
        large = await self.insert_candidate(
            key="ai:large",
            score=70,
            media_ids=media_ids[:3],
        )
        high_score = await self.insert_candidate(
            key="ai:high-score",
            score=99,
            media_ids=media_ids[3:5],
        )
        overlap = await self.insert_candidate(
            key="ai:overlap",
            score=88,
            media_ids=(media_ids[0], media_ids[3]),
        )

        page = await list_media_set_candidates_by_size(self.database)
        self.assertEqual([candidate.id for candidate in page.items], [large, high_score, overlap])

        created = await create_media_set(
            self.database,
            candidate_id=large,
            created_by=42,
        )
        self.assertEqual(set(created.media_ids), set(media_ids[:3]))

        async with self.database.acquire() as connection:
            overlap_status = await connection.fetchval(
                "SELECT status FROM media_set_candidates WHERE id = $1::BIGINT",
                overlap,
            )
            overlap_media = await connection.fetch(
                """
                SELECT media_id
                FROM media_set_candidate_items
                WHERE candidate_id = $1::BIGINT
                ORDER BY media_id
                """,
                overlap,
            )
            accepted_status = await connection.fetchval(
                "SELECT status FROM media_set_candidates WHERE id = $1::BIGINT",
                large,
            )

        self.assertEqual(accepted_status, "accepted")
        self.assertEqual(overlap_status, "ignored")
        self.assertEqual(
            [int(row["media_id"]) for row in overlap_media],
            [media_ids[3]],
        )

        remaining = await list_media_set_candidates_by_size(self.database)
        self.assertEqual([candidate.id for candidate in remaining.items], [high_score])

    async def test_duplicate_set_decision_supersedes_qwen_overlap(self) -> None:
        first, second, third = tuple(
            [await self.create_media(index) for index in range(11, 14)]
        )
        qwen_candidate = await self.insert_candidate(
            key="ai:qwen-overlap",
            score=92,
            media_ids=(first, third),
        )
        async with self.database.acquire() as connection:
            duplicate_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO media_duplicate_candidates (
                        first_media_id, second_media_id, similarity_score,
                        phash_distance, center_distance, dhash_distance, ahash_distance
                    )
                    VALUES ($1::BIGINT, $2::BIGINT, 78, 8, 8, 8, 8)
                    RETURNING id
                    """,
                    min(first, second),
                    max(first, second),
                )
            )

        visual_candidate = await create_set_candidate_from_duplicate(
            self.database,
            duplicate_candidate_id=duplicate_id,
            decided_by=42,
        )

        async with self.database.acquire() as connection:
            visual_media = await connection.fetch(
                """
                SELECT media_id
                FROM media_set_candidate_items
                WHERE candidate_id = $1::BIGINT
                ORDER BY media_id
                """,
                visual_candidate,
            )
            qwen_status = await connection.fetchval(
                "SELECT status FROM media_set_candidates WHERE id = $1::BIGINT",
                qwen_candidate,
            )
            qwen_media = await connection.fetch(
                """
                SELECT media_id
                FROM media_set_candidate_items
                WHERE candidate_id = $1::BIGINT
                ORDER BY media_id
                """,
                qwen_candidate,
            )
            duplicate_status = await connection.fetchval(
                "SELECT status FROM media_duplicate_candidates WHERE id = $1::BIGINT",
                duplicate_id,
            )

        self.assertEqual(
            [int(row["media_id"]) for row in visual_media],
            sorted((first, second)),
        )
        self.assertEqual(qwen_status, "ignored")
        self.assertEqual([int(row["media_id"]) for row in qwen_media], [third])
        self.assertEqual(duplicate_status, "ignored")


if __name__ == "__main__":
    unittest.main()
