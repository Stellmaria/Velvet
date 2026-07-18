from __future__ import annotations

import inspect
import unittest
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.error_center import CapturedLog, ErrorIncidentRepository


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        self.exited = True
        return False


def _incident_row(
    incident_id: int,
    *,
    acknowledged_at: datetime | None = None,
    acknowledged_by: int | None = None,
) -> dict[str, object]:
    now = datetime.now(UTC)
    return {
        "id": incident_id,
        "fingerprint": "f" * 64,
        "severity": "ERROR",
        "logger_name": "velvet_bot.test",
        "summary": "test incident",
        "details": "traceback",
        "occurrence_count": 2,
        "first_seen_at": now - timedelta(minutes=5),
        "last_seen_at": now,
        "acknowledged_at": acknowledged_at,
        "acknowledged_by": acknowledged_by,
        "log_chat_message_id": 777,
    }


class ErrorCenterBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def test_repository_uses_public_database_boundary(self) -> None:
        source = inspect.getsource(ErrorIncidentRepository)

        self.assertNotIn("._require_pool()", source)
        self.assertEqual(source.count("self._database.acquire()"), 8)
        for method_name in (
            "record",
            "set_log_message_id",
            "acknowledge",
            "acknowledge_all",
            "unacknowledged",
            "unacknowledged_counts",
            "digest_due",
            "mark_digest_sent",
        ):
            self.assertIn(
                "self._database.acquire()",
                inspect.getsource(getattr(ErrorIncidentRepository, method_name)),
                method_name,
            )

    async def test_record_preserves_transaction_lock_and_reopen_mapping(self) -> None:
        existing = _incident_row(
            41,
            acknowledged_at=datetime.now(UTC) - timedelta(minutes=1),
            acknowledged_by=10,
        )
        updated = _incident_row(41)
        connection = SimpleNamespace(
            fetchrow=AsyncMock(side_effect=[existing, updated]),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = ErrorIncidentRepository(database)
        captured = CapturedLog(
            fingerprint="f" * 64,
            severity="ERROR",
            logger_name="x" * 600,
            summary="failure",
            details="traceback",
            source="worker.py:10",
        )

        result = await repository.record(captured)

        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertTrue(acquire_context.entered)
        self.assertTrue(acquire_context.exited)
        self.assertTrue(transaction_context.entered)
        self.assertTrue(transaction_context.exited)
        select_call, update_call = connection.fetchrow.await_args_list
        self.assertIn("FOR UPDATE", select_call.args[0])
        self.assertEqual(select_call.args[1], "f" * 64)
        self.assertIn("occurrence_count = occurrence_count + 1", update_call.args[0])
        self.assertEqual(update_call.args[1], 41)
        self.assertEqual(len(update_call.args[3]), 500)
        self.assertTrue(result.opened)
        self.assertEqual(result.incident.id, 41)
        self.assertIsNone(result.incident.acknowledged_at)

    async def test_acknowledge_all_preserves_transaction_and_limit_clamp(self) -> None:
        rows = [_incident_row(1), _incident_row(2)]
        connection = SimpleNamespace(
            fetch=AsyncMock(return_value=rows),
            execute=AsyncMock(return_value="UPDATE 2"),
            transaction=Mock(),
        )
        transaction_context = _AsyncContext(None)
        connection.transaction.return_value = transaction_context
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = ErrorIncidentRepository(database)

        result = await repository.acknowledge_all(99, limit=999)

        database.acquire.assert_called_once_with()
        connection.transaction.assert_called_once_with()
        self.assertIn("FOR UPDATE", connection.fetch.await_args.args[0])
        self.assertEqual(connection.fetch.await_args.args[1], 100)
        self.assertIn("acknowledged_at = NOW()", connection.execute.await_args.args[0])
        self.assertEqual(connection.execute.await_args.args[1], 99)
        self.assertEqual(tuple(item.id for item in result), (1, 2))

    async def test_digest_due_preserves_cooldown_floor_and_mapping(self) -> None:
        last_sent = datetime.now(UTC) - timedelta(seconds=30)
        connection = SimpleNamespace(fetchval=AsyncMock(return_value=last_sent))
        acquire_context = _AsyncContext(connection)
        database = SimpleNamespace(acquire=Mock(return_value=acquire_context))
        repository = ErrorIncidentRepository(database)

        due = await repository.digest_due(cooldown_seconds=60)

        database.acquire.assert_called_once_with()
        self.assertFalse(due)
        self.assertIn("last_owner_digest_at", connection.fetchval.await_args.args[0])

        empty_connection = SimpleNamespace(fetchval=AsyncMock(return_value=None))
        empty_database = SimpleNamespace(
            acquire=Mock(return_value=_AsyncContext(empty_connection))
        )
        self.assertTrue(
            await ErrorIncidentRepository(empty_database).digest_due(cooldown_seconds=0)
        )


if __name__ == "__main__":
    unittest.main()
