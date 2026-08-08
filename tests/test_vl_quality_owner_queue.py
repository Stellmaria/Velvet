from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.quality_operations import QualityOperationsRepository


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


def _plan_row(*, media_ids: list[int], started_at=None) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    return {
        "id": 17,
        "requested_by": 42,
        "kind": "recent",
        "requested_limit": 25,
        "media_ids": media_ids,
        "new_count": 1,
        "legacy_pending_count": 1,
        "failed_count": 1,
        "created_at": now,
        "expires_at": now + timedelta(minutes=15),
        "started_at": started_at,
        "started_count": None,
    }


class QualityOwnerQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_plan_recent_is_dry_run_for_quality_queue(self) -> None:
        candidates = [
            {"media_id": 101, "candidate_kind": "new"},
            {"media_id": 99, "candidate_kind": "legacy_pending"},
            {"media_id": 95, "candidate_kind": "failed"},
        ]
        connection = SimpleNamespace(
            execute=AsyncMock(return_value="DELETE 0"),
            fetch=AsyncMock(return_value=candidates),
            fetchrow=AsyncMock(return_value=_plan_row(media_ids=[101, 99, 95])),
            transaction=Mock(return_value=_AsyncContext(None)),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        plan = await QualityOperationsRepository(database).plan_recent(
            requested_by=42,
            limit=25,
        )

        self.assertEqual(plan.plan_id, 17)
        self.assertEqual(plan.media_ids, (101, 99, 95))
        self.assertEqual(plan.new_count, 1)
        self.assertEqual(plan.legacy_pending_count, 1)
        self.assertEqual(plan.failed_count, 1)
        self.assertEqual(connection.fetch.await_args.args[-1], 25)
        all_sql = "\n".join(
            str(call.args[0]) for call in connection.execute.await_args_list
        )
        self.assertNotIn("INSERT INTO media_ai_quality_checks", all_sql)
        self.assertIn("INSERT INTO media_ai_quality_queue_plans", connection.fetchrow.await_args.args[0])

    async def test_start_plan_queues_only_exact_persisted_media_ids(self) -> None:
        plan_row = _plan_row(media_ids=[101, 99, 95])
        connection = SimpleNamespace(
            fetchrow=AsyncMock(return_value=plan_row),
            fetch=AsyncMock(
                return_value=[{"media_id": 101}, {"media_id": 99}, {"media_id": 95}]
            ),
            execute=AsyncMock(return_value="UPDATE 1"),
            transaction=Mock(return_value=_AsyncContext(None)),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        count = await QualityOperationsRepository(database).start_plan(
            17,
            requested_by=42,
        )

        self.assertEqual(count, 3)
        queue_sql, media_ids, plan_id = connection.fetch.await_args.args
        self.assertIn("INSERT INTO media_ai_quality_checks", queue_sql)
        self.assertIn("queue_plan_id", queue_sql)
        self.assertEqual(media_ids, [101, 99, 95])
        self.assertEqual(plan_id, 17)
        self.assertIn(
            "started_at = NOW()",
            connection.execute.await_args.args[0],
        )
        self.assertEqual(connection.execute.await_args.args[1:], (17, 3))

    async def test_start_plan_rejects_wrong_owner_without_queue_mutation(self) -> None:
        connection = SimpleNamespace(
            fetchrow=AsyncMock(return_value=None),
            fetch=AsyncMock(),
            execute=AsyncMock(),
            transaction=Mock(return_value=_AsyncContext(None)),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        with self.assertRaisesRegex(ValueError, "не найден"):
            await QualityOperationsRepository(database).start_plan(
                17,
                requested_by=777,
            )

        connection.fetch.assert_not_awaited()
        connection.execute.assert_not_awaited()

    def test_migration_quarantines_pre_plan_active_backlog(self) -> None:
        migration = Path("migrations/zz002_quality_owner_queue.sql").read_text(
            encoding="utf-8"
        )

        self.assertIn("media_ai_quality_queue_plans", migration)
        self.assertIn("queue_plan_id", migration)
        self.assertIn("status IN ('pending', 'processing', 'error')", migration)
        self.assertIn("Legacy global quality backlog quarantined", migration)


if __name__ == "__main__":
    unittest.main()
