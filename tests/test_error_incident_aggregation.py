from __future__ import annotations

import inspect
import unittest
from dataclasses import replace
from datetime import UTC, datetime

from velvet_bot.error_center import (
    CapturedLog,
    ErrorIncident,
    ErrorIncidentCenter,
    ErrorIncidentRepository,
    RecordedIncident,
)


_SEVERITY_RANK = {"WARNING": 1, "ERROR": 2, "CRITICAL": 3}


class FakeRepository:
    def __init__(self) -> None:
        self.incidents: dict[str, ErrorIncident] = {}
        self.record_calls = 0
        self.batch_calls = 0
        self.fail_batch = False

    async def record(self, captured: CapturedLog) -> RecordedIncident:
        self.record_calls += 1
        now = datetime.now(UTC)
        existing = self.incidents.get(captured.fingerprint)
        opened = existing is None or existing.acknowledged_at is not None
        if existing is None:
            incident = ErrorIncident(
                id=len(self.incidents) + 1,
                fingerprint=captured.fingerprint,
                severity=captured.severity,
                logger_name=captured.logger_name,
                summary=captured.summary,
                details=captured.details,
                occurrence_count=1,
                first_seen_at=now,
                last_seen_at=now,
                acknowledged_at=None,
                acknowledged_by=None,
                log_chat_message_id=10,
            )
        else:
            severity = max(
                (existing.severity, captured.severity),
                key=_SEVERITY_RANK.__getitem__,
            )
            incident = replace(
                existing,
                severity=severity,
                occurrence_count=existing.occurrence_count + 1,
                last_seen_at=now,
                acknowledged_at=None,
                acknowledged_by=None,
                log_chat_message_id=(
                    None if existing.acknowledged_at is not None
                    else existing.log_chat_message_id
                ),
            )
        self.incidents[captured.fingerprint] = incident
        return RecordedIncident(incident=incident, opened=opened)

    async def record_batch(
        self,
        captured: CapturedLog,
        *,
        count: int,
        last_seen_at: datetime,
    ) -> RecordedIncident:
        self.batch_calls += 1
        if self.fail_batch:
            raise RuntimeError("database unavailable")
        existing = self.incidents[captured.fingerprint]
        severity = max(
            (existing.severity, captured.severity),
            key=_SEVERITY_RANK.__getitem__,
        )
        reopened = existing.acknowledged_at is not None
        incident = replace(
            existing,
            severity=severity,
            occurrence_count=existing.occurrence_count + count,
            last_seen_at=last_seen_at,
            acknowledged_at=None,
            acknowledged_by=None,
            log_chat_message_id=None if reopened else existing.log_chat_message_id,
        )
        self.incidents[captured.fingerprint] = incident
        return RecordedIncident(incident=incident, opened=reopened)

    async def acknowledge(self, incident_id: int, user_id: int) -> ErrorIncident | None:
        for fingerprint, incident in self.incidents.items():
            if incident.id != incident_id:
                continue
            acknowledged = replace(
                incident,
                acknowledged_at=datetime.now(UTC),
                acknowledged_by=user_id,
            )
            self.incidents[fingerprint] = acknowledged
            return acknowledged
        return None

    async def acknowledge_all(self, user_id: int, *, limit: int = 50) -> tuple[ErrorIncident, ...]:
        acknowledged: list[ErrorIncident] = []
        for fingerprint, incident in tuple(self.incidents.items())[:limit]:
            updated = replace(
                incident,
                acknowledged_at=datetime.now(UTC),
                acknowledged_by=user_id,
            )
            self.incidents[fingerprint] = updated
            acknowledged.append(updated)
        return tuple(acknowledged)


class QuietCenter(ErrorIncidentCenter):
    def __init__(self, repository: FakeRepository) -> None:
        super().__init__(
            bot=None,  # type: ignore[arg-type]
            repository=repository,  # type: ignore[arg-type]
            log_chat_id=None,
            owner_user_ids=frozenset(),
        )
        self.published: list[ErrorIncident] = []
        self.digest_cooldowns: list[int] = []

    async def _publish_to_log_chat(self, incident: ErrorIncident) -> None:
        self.published.append(incident)

    async def _send_owner_digest(self, *, cooldown_seconds: int) -> int:
        self.digest_cooldowns.append(cooldown_seconds)
        return 0


def captured(
    fingerprint: str = "a" * 64,
    *,
    severity: str = "ERROR",
) -> CapturedLog:
    return CapturedLog(
        fingerprint=fingerprint,
        severity=severity,
        logger_name="velvet_bot.test",
        summary="Synthetic incident",
        details=None,
        source="tests/test_error_incident_aggregation.py:1",
    )


class ErrorIncidentAggregationTests(unittest.IsolatedAsyncioTestCase):
    async def test_thousand_repeats_use_one_batch_write(self) -> None:
        repository = FakeRepository()
        center = QuietCenter(repository)
        event = captured()

        await center._process(event)
        for _ in range(1000):
            await center._process(event)

        self.assertEqual(1, repository.record_calls)
        self.assertEqual(0, repository.batch_calls)
        self.assertEqual(1, len(center.published))
        self.assertEqual(1000, center._pending[event.fingerprint][1])

        await center.flush_pending()

        self.assertEqual(1, repository.batch_calls)
        self.assertEqual(1001, repository.incidents[event.fingerprint].occurrence_count)
        self.assertEqual(2, len(center.published))
        metrics = center.aggregation_metrics()
        self.assertEqual(1000, metrics["aggregated_repeats"])
        self.assertEqual(1000, metrics["notification_suppressions"])
        self.assertEqual(1, metrics["rows_updated"])

    async def test_critical_escalation_flushes_and_bypasses_digest_cooldown(self) -> None:
        repository = FakeRepository()
        center = QuietCenter(repository)
        warning = captured(severity="WARNING")

        await center._process(warning)
        await center._process(warning)
        await center._process(captured(severity="CRITICAL"))

        incident = repository.incidents[warning.fingerprint]
        self.assertEqual("CRITICAL", incident.severity)
        self.assertEqual(3, incident.occurrence_count)
        self.assertEqual(2, repository.record_calls)
        self.assertEqual(1, repository.batch_calls)
        self.assertEqual([], list(center._pending))
        self.assertEqual([120, 0], center.digest_cooldowns)

    async def test_failed_flush_keeps_pending_counts_for_retry(self) -> None:
        repository = FakeRepository()
        center = QuietCenter(repository)
        event = captured()
        await center._process(event)
        await center._process(event)
        repository.fail_batch = True

        await center.flush_pending()

        self.assertEqual(1, center._pending[event.fingerprint][1])
        self.assertEqual(1, center.aggregation_metrics()["flush_errors"])
        repository.fail_batch = False
        await center.flush_pending()
        self.assertNotIn(event.fingerprint, center._pending)
        self.assertEqual(2, repository.incidents[event.fingerprint].occurrence_count)

    async def test_acknowledge_flushes_before_marking_and_next_repeat_reopens(self) -> None:
        repository = FakeRepository()
        center = QuietCenter(repository)
        event = captured()
        await center._process(event)
        await center._process(event)

        self.assertTrue(await center.acknowledge_incident(1, 17))
        self.assertEqual(2, repository.incidents[event.fingerprint].occurrence_count)
        self.assertIsNotNone(repository.incidents[event.fingerprint].acknowledged_at)
        self.assertFalse(center._known)

        await center._process(event)

        self.assertEqual(2, repository.record_calls)
        self.assertIsNone(repository.incidents[event.fingerprint].acknowledged_at)
        self.assertEqual(3, repository.incidents[event.fingerprint].occurrence_count)

    async def test_shutdown_performs_final_flush(self) -> None:
        repository = FakeRepository()
        center = QuietCenter(repository)
        event = captured()
        await center._process(event)
        await center._process(event)

        await center.stop()

        self.assertFalse(center._pending)
        self.assertEqual(2, repository.incidents[event.fingerprint].occurrence_count)

    def test_repository_batch_is_atomic_and_does_not_rewrite_payload(self) -> None:
        source = inspect.getsource(ErrorIncidentRepository.record_batch)
        self.assertIn("occurrence_count = incident.occurrence_count + $3", source)
        self.assertIn("FOR UPDATE", source)
        update_clause = source.split("SET severity", 1)[1].split("FROM target", 1)[0]
        self.assertNotIn("summary =", update_clause)
        self.assertNotIn("details =", update_clause)


if __name__ == "__main__":
    unittest.main()
