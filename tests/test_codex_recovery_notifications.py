from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from velvet_bot.services.codex_recovery_notifications import (
    CodexAvailabilitySnapshot,
    CodexRecoveryNotificationMonitor,
)


class FakeBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.error: Exception | None = None

    async def send_message(self, **kwargs: object) -> object:
        if self.error is not None:
            raise self.error
        self.messages.append(dict(kwargs))
        return object()


class SnapshotSource:
    def __init__(self, values: dict[str, CodexAvailabilitySnapshot]) -> None:
        self.values = values

    async def __call__(self, project: str) -> CodexAvailabilitySnapshot:
        return self.values[project]


def limited(project: str, checked_at: int = 1_000) -> CodexAvailabilitySnapshot:
    return CodexAvailabilitySnapshot(
        project=project,
        codex_available=False,
        provider_available=False,
        reason="subscription_limit",
        provider_reason="subscription_limit",
        last_checked_at=checked_at,
        last_check_source="periodic_5h",
        last_error=None,
        codex_available_at=5_000,
        next_periodic_check_at=19_000,
        plan_type="plus",
    )


def available(project: str, checked_at: int = 2_000) -> CodexAvailabilitySnapshot:
    return CodexAvailabilitySnapshot(
        project=project,
        codex_available=True,
        provider_available=True,
        reason="available",
        provider_reason="available",
        last_checked_at=checked_at,
        last_check_source="periodic_5h",
        last_error=None,
        codex_available_at=None,
        next_periodic_check_at=20_000,
        plan_type="plus",
    )


class CodexRecoveryNotificationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state_path = Path(self.directory.name) / "codex-recovery.json"
        self.bot = FakeBot()
        self.source = SnapshotSource({
            "velvet": limited("velvet"),
            "max": limited("max"),
        })

    def monitor(self) -> CodexRecoveryNotificationMonitor:
        return CodexRecoveryNotificationMonitor(
            bot=self.bot,  # type: ignore[arg-type]
            owner_chat_id=123,
            fetch_snapshot=self.source,
            state_path=self.state_path,
        )

    async def test_limit_then_live_recovery_sends_once_and_persists_dedupe(self) -> None:
        monitor = self.monitor()
        self.assertEqual(0, await monitor.process_once())
        self.assertEqual([], self.bot.messages)

        self.source.values = {
            "velvet": available("velvet", 2_000),
            "max": available("max", 2_001),
        }
        self.assertEqual(1, await monitor.process_once())
        self.assertEqual(1, len(self.bot.messages))
        text = str(self.bot.messages[0]["text"])
        self.assertIn("Codex снова доступен", text)
        self.assertIn("primary Codex routing включён", text)
        self.assertIn("План: Plus", text)

        restarted = self.monitor()
        self.assertEqual(0, await restarted.process_once())
        self.assertEqual(1, len(self.bot.messages))
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertIsNotNone(persisted["last_notified_event_id"])
        self.assertIsNone(persisted["active_limit_event_id"])

    async def test_delivery_failure_is_claimed_before_send_and_not_retried(self) -> None:
        monitor = self.monitor()
        await monitor.process_once()
        self.source.values = {
            "velvet": available("velvet", 2_000),
            "max": available("max", 2_001),
        }
        self.bot.error = RuntimeError("telegram unavailable")
        with self.assertRaisesRegex(RuntimeError, "telegram unavailable"):
            await monitor.process_once()

        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertIsNotNone(persisted["last_notified_event_id"])
        self.assertIsNone(persisted["active_limit_event_id"])

        self.bot.error = None
        restarted = self.monitor()
        self.assertEqual(0, await restarted.process_once())
        self.assertEqual([], self.bot.messages)

    async def test_waits_until_both_projects_confirm_recovery(self) -> None:
        monitor = self.monitor()
        await monitor.process_once()
        self.source.values = {
            "velvet": available("velvet", 2_000),
            "max": limited("max", 1_100),
        }
        self.assertEqual(0, await monitor.process_once())
        self.assertEqual([], self.bot.messages)

        self.source.values["max"] = available("max", 2_100)
        self.assertEqual(1, await monitor.process_once())
        self.assertEqual(1, len(self.bot.messages))

    async def test_probe_error_never_confirms_recovery(self) -> None:
        monitor = self.monitor()
        await monitor.process_once()
        broken = available("velvet", 2_000)
        self.source.values = {
            "velvet": CodexAvailabilitySnapshot(
                project=broken.project,
                codex_available=broken.codex_available,
                provider_available=broken.provider_available,
                reason=broken.reason,
                provider_reason=broken.provider_reason,
                last_checked_at=broken.last_checked_at,
                last_check_source="periodic_5h",
                last_error="provider timeout",
                codex_available_at=broken.codex_available_at,
                next_periodic_check_at=broken.next_periodic_check_at,
                plan_type=broken.plan_type,
            ),
            "max": available("max", 2_001),
        }
        self.assertEqual(0, await monitor.process_once())
        self.assertEqual([], self.bot.messages)

    async def test_startup_available_without_proven_limit_does_not_notify(self) -> None:
        self.source.values = {
            "velvet": available("velvet"),
            "max": available("max"),
        }
        self.assertEqual(0, await self.monitor().process_once())
        self.assertEqual([], self.bot.messages)
        self.assertFalse(self.state_path.exists())

    async def test_manual_hold_clear_without_subscription_limit_does_not_notify(self) -> None:
        held = CodexAvailabilitySnapshot(
            project="velvet",
            codex_available=False,
            provider_available=True,
            reason="manual_hold",
            provider_reason="available",
            last_checked_at=1_000,
            last_check_source="operator_refresh",
            last_error=None,
            codex_available_at=None,
            next_periodic_check_at=19_000,
            plan_type="plus",
        )
        self.source.values = {"velvet": held, "max": held}
        monitor = self.monitor()
        self.assertEqual(0, await monitor.process_once())
        self.source.values = {
            "velvet": available("velvet", 2_000),
            "max": available("max", 2_000),
        }
        self.assertEqual(0, await monitor.process_once())
        self.assertEqual([], self.bot.messages)

    async def test_recovery_must_be_newer_than_limited_probe(self) -> None:
        monitor = self.monitor()
        await monitor.process_once()
        self.source.values = {
            "velvet": available("velvet", 1_000),
            "max": available("max", 1_000),
        }
        self.assertEqual(0, await monitor.process_once())
        self.assertEqual([], self.bot.messages)

    def test_monitor_reads_persisted_capabilities_not_rate_limits(self) -> None:
        source = Path("velvet_bot/services/codex_recovery_notifications.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("/capabilities", source)
        self.assertNotIn("/rate-limits", source)


if __name__ == "__main__":
    unittest.main()
