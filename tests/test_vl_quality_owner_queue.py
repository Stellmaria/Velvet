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
        connection = SimpleNamespace(
            fetchrow=AsyncMock(return_value=_plan_row(media_ids=[101, 99, 95])),
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
        create_sql, requested_by, kind, limit = connection.fetchrow.await_args.args
        self.assertIn("INSERT INTO media_ai_quality_queue_plans", create_sql)
        self.assertNotIn("INSERT INTO media_ai_quality_checks", create_sql)
        self.assertEqual((requested_by, kind, limit), (42, "recent", 25))

    async def test_start_plan_queues_only_persisted_plan_media_ids(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=3))
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        count = await QualityOperationsRepository(database).start_plan(
            17,
            requested_by=42,
        )

        self.assertEqual(count, 3)
        start_sql, plan_id, requested_by = connection.fetchval.await_args.args
        self.assertIn("selected_plan.media_ids", start_sql)
        self.assertIn("INSERT INTO media_ai_quality_checks", start_sql)
        self.assertIn("queue_plan_id", start_sql)
        self.assertIn("started_at = NOW()", start_sql)
        self.assertEqual((plan_id, requested_by), (17, 42))

    async def test_start_plan_rejects_wrong_owner_or_stale_plan(self) -> None:
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=None))
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        with self.assertRaisesRegex(ValueError, "не найден, устарел"):
            await QualityOperationsRepository(database).start_plan(
                17,
                requested_by=777,
            )

        start_sql, plan_id, requested_by = connection.fetchval.await_args.args
        self.assertIn("requested_by = $2::BIGINT", start_sql)
        self.assertIn("started_at IS NULL", start_sql)
        self.assertIn("expires_at > NOW()", start_sql)
        self.assertEqual((plan_id, requested_by), (17, 777))

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
