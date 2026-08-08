from __future__ import annotations

import unittest
from typing import cast

from velvet_bot.database import Database
from velvet_bot.presentation.telegram.storage_librarian import (
    _STALE_RUNNING_SECONDS,
    _recover_stale_running_jobs,
)


class _FakeConnection:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.query = ""
        self.args: tuple[object, ...] = ()

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.query = query
        self.args = args
        return self.rows


class _AcquireContext:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    async def __aenter__(self) -> _FakeConnection:
        return self.connection

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None


class _FakeDatabase:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    def acquire(self) -> _AcquireContext:
        return _AcquireContext(self.connection)


class StorageLibrarianStaleRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_requeues_or_fails_without_resetting_attempts(self) -> None:
        connection = _FakeConnection(
            [
                {"status": "queued"},
                {"status": "queued"},
                {"status": "failed"},
            ]
        )
        database = cast(Database, _FakeDatabase(connection))

        recovered = await _recover_stale_running_jobs(database)

        self.assertEqual(recovered, (2, 1))
        self.assertEqual(connection.args, (_STALE_RUNNING_SECONDS,))
        normalized = " ".join(connection.query.split())
        self.assertIn("WHERE status = 'running'", normalized)
        self.assertIn("locked_at IS NULL", normalized)
        self.assertIn("attempts >= max_attempts", normalized)
        self.assertIn("worker_id = NULL", normalized)
        self.assertIn("locked_at = NULL", normalized)
        self.assertNotIn("attempts = 0", normalized)
        self.assertNotIn("attempts = attempts - 1", normalized)

    async def test_recovery_is_noop_when_no_stale_jobs_exist(self) -> None:
        connection = _FakeConnection([])
        database = cast(Database, _FakeDatabase(connection))

        recovered = await _recover_stale_running_jobs(database)

        self.assertEqual(recovered, (0, 0))

    def test_stale_window_is_longer_than_normal_inference_timeout(self) -> None:
        self.assertEqual(_STALE_RUNNING_SECONDS, 15 * 60)
        self.assertGreater(_STALE_RUNNING_SECONDS, 180)


if __name__ == "__main__":
    unittest.main()
