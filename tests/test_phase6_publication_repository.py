import os
import unittest

from velvet_bot.database import Database
from velvet_bot.domains.publication.repository import PublicationRepository


@unittest.skipUnless(
    os.getenv("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is required for PostgreSQL integration tests",
)
class PublicationRepositoryIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.database = Database(os.environ["TEST_DATABASE_URL"])
        await self.database.initialize()
        self.repository = PublicationRepository(self.database)
        self.created_ids: list[int] = []

    async def asyncTearDown(self) -> None:
        if self.created_ids:
            async with self.database._require_pool().acquire() as connection:
                await connection.execute(
                    "DELETE FROM publication_drafts WHERE id = ANY($1::BIGINT[])",
                    self.created_ids,
                )
        await self.database.close()

    async def _create_draft(self, *, status: str) -> int:
        async with self.database._require_pool().acquire() as connection:
            draft_id = int(
                await connection.fetchval(
                    """
                    INSERT INTO publication_drafts (
                        owner_id,
                        target_chat_id,
                        text_content,
                        status,
                        content_hash,
                        validation_status,
                        scheduled_at
                    )
                    VALUES (
                        999001,
                        -1003802812639,
                        'Phase 6 repository test',
                        $1::VARCHAR,
                        $2::CHAR(64),
                        'passed',
                        CASE
                            WHEN $1::VARCHAR = 'scheduled'
                                THEN NOW() - INTERVAL '1 minute'
                            ELSE NULL
                        END
                    )
                    RETURNING id
                    """,
                    status,
                    f"{len(self.created_ids) + 1:064x}",
                )
            )
        self.created_ids.append(draft_id)
        return draft_id

    async def test_claim_publish_and_event_are_atomic(self) -> None:
        draft_id = await self._create_draft(status="scheduled")

        due = await self.repository.list_due_draft_ids(limit=10)
        self.assertIn(draft_id, due)
        self.assertTrue(await self.repository.claim_for_publishing(draft_id))
        self.assertFalse(await self.repository.claim_for_publishing(draft_id))

        await self.repository.mark_published(
            draft_id,
            message_ids=[101, 102],
            actor_id=999001,
        )

        async with self.database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT status, attempt_count, published_message_ids, last_error
                FROM publication_drafts
                WHERE id = $1::BIGINT
                """,
                draft_id,
            )
            event = await connection.fetchrow(
                """
                SELECT event_type, actor_id, details
                FROM publication_events
                WHERE draft_id = $1::BIGINT
                ORDER BY id DESC
                LIMIT 1
                """,
                draft_id,
            )

        self.assertEqual("published", row["status"])
        self.assertEqual(1, row["attempt_count"])
        self.assertEqual([101, 102], list(row["published_message_ids"]))
        self.assertIsNone(row["last_error"])
        self.assertEqual("published", event["event_type"])
        self.assertEqual(999001, event["actor_id"])
        self.assertIn("101", str(event["details"]))

    async def test_error_transition_is_recorded(self) -> None:
        draft_id = await self._create_draft(status="checked")
        self.assertTrue(await self.repository.claim_for_publishing(draft_id))

        await self.repository.mark_error(
            draft_id,
            error=RuntimeError("Telegram unavailable"),
            actor_id=None,
        )

        async with self.database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                "SELECT status, last_error FROM publication_drafts WHERE id = $1::BIGINT",
                draft_id,
            )
            event_type = await connection.fetchval(
                """
                SELECT event_type
                FROM publication_events
                WHERE draft_id = $1::BIGINT
                ORDER BY id DESC
                LIMIT 1
                """,
                draft_id,
            )

        self.assertEqual("error", row["status"])
        self.assertEqual("Telegram unavailable", row["last_error"])
        self.assertEqual("error", event_type)


if __name__ == "__main__":
    unittest.main()
