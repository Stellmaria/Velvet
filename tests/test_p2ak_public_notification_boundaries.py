from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

import velvet_bot.app.public_notifications as app_module
import velvet_bot.presentation.telegram.public_notifications as delivery_module
import velvet_bot.public_notifications as worker_module
from velvet_bot.domains.public_archive import PendingPublicNotification


class FakeForbiddenError(Exception):
    pass


class FakeBadRequest(Exception):
    pass


class FakeNotificationService:
    def __init__(self, pending) -> None:
        self.pending = list(pending)
        self.list_limits: list[int] = []
        self.removed: list[dict[str, int]] = []
        self.marked: list[object] = []

    async def list_pending_notifications(self, *, limit: int):
        self.list_limits.append(limit)
        return list(self.pending[:limit])

    async def remove_subscription(self, **kwargs) -> None:
        self.removed.append(kwargs)

    async def mark_notification_delivered(self, notification) -> None:
        self.marked.append(notification)


class FakeBot:
    def __init__(self, outcomes) -> None:
        self.outcomes = dict(outcomes)
        self.calls: list[dict[str, object]] = []

    async def send_message(self, **kwargs) -> None:
        self.calls.append(kwargs)
        outcome = self.outcomes.get(kwargs["chat_id"])
        if outcome is not None:
            raise outcome


class PublicNotificationDeliveryBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_forbidden = delivery_module.TelegramForbiddenError
        self.original_bad_request = delivery_module.TelegramBadRequest
        self.original_keyboard = delivery_module.notification_keyboard
        delivery_module.TelegramForbiddenError = FakeForbiddenError
        delivery_module.TelegramBadRequest = FakeBadRequest
        delivery_module.notification_keyboard = (
            lambda character_id, media_id, *, workspace_id=1: (
                workspace_id,
                character_id,
                media_id,
            )
        )

    def tearDown(self) -> None:
        delivery_module.TelegramForbiddenError = self.original_forbidden
        delivery_module.TelegramBadRequest = self.original_bad_request
        delivery_module.notification_keyboard = self.original_keyboard

    @staticmethod
    def _notification(user_id: int, character_id: int, media_id: int):
        return SimpleNamespace(
            user_id=user_id,
            character_id=character_id,
            media_id=media_id,
            character_name=f"Character {character_id}",
        )

    async def test_unexpected_failure_is_isolated_and_next_subscribers_continue(self) -> None:
        first = self._notification(101, 1, 11)
        second = self._notification(102, 2, 12)
        third = self._notification(103, 3, 13)
        service = FakeNotificationService([first, second, third])
        bot = FakeBot(
            {
                101: RuntimeError("temporary send failure"),
                103: FakeForbiddenError("blocked"),
            }
        )
        dispatcher = delivery_module.TelegramPublicNotificationDispatcher(
            bot=bot,
            service=service,
            workspace_id=7,
        )

        with self.assertLogs(delivery_module.logger, level="ERROR") as captured:
            delivered = await dispatcher.process_once(limit=9)

        self.assertEqual(delivered, 1)
        self.assertEqual(service.list_limits, [9])
        self.assertEqual([call["chat_id"] for call in bot.calls], [101, 102, 103])
        self.assertEqual(
            [call["reply_markup"] for call in bot.calls],
            [(7, 1, 11), (7, 2, 12), (7, 3, 13)],
        )
        self.assertEqual(service.marked, [second])
        self.assertEqual(
            service.removed,
            [{"character_id": 3, "user_id": 103}],
        )
        rendered = "\n".join(captured.output)
        self.assertIn("Failed to deliver notification to 101", rendered)
        self.assertIn("temporary send failure", rendered)

    async def test_delivery_cancellation_stops_batch_and_propagates(self) -> None:
        first = self._notification(101, 1, 11)
        second = self._notification(102, 2, 12)
        service = FakeNotificationService([first, second])
        bot = FakeBot({101: asyncio.CancelledError()})
        dispatcher = delivery_module.TelegramPublicNotificationDispatcher(
            bot=bot,
            service=service,
        )

        with self.assertRaises(asyncio.CancelledError):
            await dispatcher.process_once()

        self.assertEqual([call["chat_id"] for call in bot.calls], [101])
        self.assertEqual(service.marked, [])
        self.assertEqual(service.removed, [])


class _Acquire:
    def __init__(self, connection) -> None:
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


class WorkspaceNotificationDispatcherTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_scans_system_and_public_personal_workspaces_with_one_limit(self) -> None:
        connection = SimpleNamespace(
            fetch=AsyncMock(return_value=[{"id": 1}, {"id": 5}])
        )
        database = SimpleNamespace(acquire=lambda: _Acquire(connection))
        services = {
            1: FakeNotificationService(
                [PendingPublicNotification(11, "System", 101, 201)]
            ),
            5: FakeNotificationService(
                [
                    PendingPublicNotification(12, "Personal", 102, 202),
                    PendingPublicNotification(12, "Personal", 103, 203),
                ]
            ),
        }
        delivered_batches: list[tuple[int, tuple[PendingPublicNotification, ...]]] = []

        class FakeScopedDispatcher:
            def __init__(self, *, bot, service, workspace_id: int) -> None:
                self.workspace_id = workspace_id

            async def deliver(self, pending) -> int:
                batch = tuple(pending)
                delivered_batches.append((self.workspace_id, batch))
                return len(batch)

        original_builder = app_module.build_public_archive_service
        original_dispatcher = app_module.TelegramPublicNotificationDispatcher
        app_module.build_public_archive_service = (
            lambda database, *, workspace_id: services[workspace_id]
        )
        app_module.TelegramPublicNotificationDispatcher = FakeScopedDispatcher
        try:
            dispatcher = app_module.WorkspacePublicNotificationDispatcher(
                bot=object(),
                database=database,
            )
            delivered = await dispatcher.process_once(limit=2)
        finally:
            app_module.build_public_archive_service = original_builder
            app_module.TelegramPublicNotificationDispatcher = original_dispatcher

        self.assertEqual(delivered, 2)
        self.assertEqual(services[1].list_limits, [2])
        self.assertEqual(services[5].list_limits, [1])
        self.assertEqual(
            [
                (workspace_id, [item.workspace_id for item in batch])
                for workspace_id, batch in delivered_batches
            ],
            [(1, [1]), (5, [5])],
        )


class FakeDispatcher:
    outcomes: list[BaseException | None] = []

    def __init__(self) -> None:
        self.calls = 0

    async def process_once(self) -> None:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if outcome is not None:
            raise outcome


class PublicNotificationWorkerBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_recovers_after_batch_failure_and_honors_minimum_interval(self) -> None:
        original_builder = worker_module.build_public_notification_dispatcher
        original_sleep = worker_module.asyncio.sleep
        dispatcher = FakeDispatcher()
        FakeDispatcher.outcomes = [RuntimeError("batch failed"), asyncio.CancelledError()]
        sleeps: list[float] = []

        async def fake_sleep(delay: float) -> None:
            sleeps.append(delay)

        worker_module.build_public_notification_dispatcher = (
            lambda bot, database: dispatcher
        )
        worker_module.asyncio.sleep = fake_sleep
        try:
            with self.assertLogs(worker_module.logger, level="ERROR") as captured:
                with self.assertRaises(asyncio.CancelledError):
                    await worker_module.run_public_notification_worker(
                        object(),
                        object(),
                        interval_seconds=0.2,
                    )
        finally:
            worker_module.build_public_notification_dispatcher = original_builder
            worker_module.asyncio.sleep = original_sleep

        self.assertEqual(dispatcher.calls, 2)
        self.assertEqual(sleeps, [1.0])
        rendered = "\n".join(captured.output)
        self.assertIn("Public notification worker iteration failed", rendered)
        self.assertIn("batch failed", rendered)

    async def test_worker_cancellation_is_terminal_without_failure_log(self) -> None:
        original_builder = worker_module.build_public_notification_dispatcher
        dispatcher = FakeDispatcher()
        FakeDispatcher.outcomes = [asyncio.CancelledError()]
        worker_module.build_public_notification_dispatcher = (
            lambda bot, database: dispatcher
        )
        try:
            with self.assertNoLogs(worker_module.logger, level="ERROR"):
                with self.assertRaises(asyncio.CancelledError):
                    await worker_module.run_public_notification_worker(
                        object(),
                        object(),
                    )
        finally:
            worker_module.build_public_notification_dispatcher = original_builder

        self.assertEqual(dispatcher.calls, 1)


if __name__ == "__main__":
    unittest.main()
