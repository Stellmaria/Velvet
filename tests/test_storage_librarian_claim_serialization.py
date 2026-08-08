from __future__ import annotations

import unittest
from typing import Any

from velvet_bot.domains.telegram_storage.arthur_repository import (
    ArthurStorageLibrarianRepository,
)
from velvet_bot.domains.telegram_storage.librarian_afk_repository import (
    StorageLibrarianAfkRepository,
)
from velvet_bot.domains.telegram_storage.librarian_repository import (
    StorageLibrarianRepository,
)


class _AsyncContext:
    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, *args: object) -> None:
        return None


class _FakeConnection:
    def __init__(self, row: dict[str, object] | None = None) -> None:
        self.row = row or {
            "id": 17,
            "storage_object_id": 42,
            "attempts": 1,
            "max_attempts": 3,
        }
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetchrow_calls: list[tuple[str, tuple[object, ...]]] = []
        self.transaction_entries = 0

    def transaction(self) -> _AsyncContext:
        self.transaction_entries += 1
        return _AsyncContext(self)

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, args))
        return "SELECT 1"

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        self.fetchrow_calls.append((query, args))
        return self.row


class _FakeDatabase:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    def acquire(self) -> _AsyncContext:
        return _AsyncContext(self.connection)


def _assert_shared_claim_contract(
    testcase: unittest.TestCase,
    connection: _FakeConnection,
    *,
    expected_args: tuple[object, object, object],
) -> None:
    testcase.assertEqual(1, connection.transaction_entries)
    testcase.assertEqual(1, len(connection.execute_calls))
    advisory_sql, advisory_args = connection.execute_calls[0]
    testcase.assertIn("pg_advisory_xact_lock", advisory_sql)
    testcase.assertEqual(1, len(advisory_args))

    testcase.assertEqual(1, len(connection.fetchrow_calls))
    claim_sql, claim_args = connection.fetchrow_calls[0]
    testcase.assertIn("active.status = 'running'", claim_sql)
    testcase.assertIn("NOT EXISTS", claim_sql)
    testcase.assertIn("FOR UPDATE OF candidate SKIP LOCKED", claim_sql)
    testcase.assertEqual(expected_args, claim_args)


class StorageLibrarianClaimSerializationTests(unittest.IsolatedAsyncioTestCase):
    async def test_base_claim_serializes_and_blocks_when_any_job_is_running(self) -> None:
        connection = _FakeConnection()
        repository = StorageLibrarianRepository(  # type: ignore[arg-type]
            _FakeDatabase(connection)
        )

        job = await repository.claim_next("main-worker")

        assert job is not None
        self.assertEqual(42, job.storage_object_id)
        _assert_shared_claim_contract(
            self,
            connection,
            expected_args=("main-worker", None, None),
        )

    async def test_arthur_target_claim_keeps_exact_object_inside_shared_gate(self) -> None:
        connection = _FakeConnection()
        repository = ArthurStorageLibrarianRepository(  # type: ignore[arg-type]
            _FakeDatabase(connection),
            target_object_id=42,
        )

        job = await repository.claim_next("arthur-worker")

        assert job is not None
        self.assertEqual(42, job.storage_object_id)
        _assert_shared_claim_contract(
            self,
            connection,
            expected_args=("arthur-worker", 42, None),
        )

    async def test_afk_claim_keeps_cutoff_inside_shared_gate(self) -> None:
        connection = _FakeConnection()
        repository = StorageLibrarianAfkRepository(  # type: ignore[arg-type]
            _FakeDatabase(connection),
            min_object_id=100,
        )

        job = await repository.claim_next("afk-worker")

        assert job is not None
        _assert_shared_claim_contract(
            self,
            connection,
            expected_args=("afk-worker", None, 100),
        )

    async def test_busy_or_empty_queue_returns_no_job(self) -> None:
        connection = _FakeConnection(row=None)
        connection.row = None
        repository = StorageLibrarianRepository(  # type: ignore[arg-type]
            _FakeDatabase(connection)
        )

        self.assertIsNone(await repository.claim_next("second-worker"))
        _assert_shared_claim_contract(
            self,
            connection,
            expected_args=("second-worker", None, None),
        )


if __name__ == "__main__":
    unittest.main()
