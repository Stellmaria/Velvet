from __future__ import annotations

import asyncio
import unittest

import velvet_bot.presentation.telegram.routers.supervisor.console as module


class SupervisorConsoleWatcherBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_operation = module._operation
        self.original_safe_edit = module._safe_edit
        self.original_operation_text = module.console_operation_text
        self.original_operation_keyboard = module.console_operation_keyboard
        self.original_operation_finished = module.console_operation_finished

        module.console_operation_text = lambda operation: "rendered"
        module.console_operation_keyboard = lambda operation_id, **kwargs: "keyboard"
        module.console_operation_finished = lambda operation: False

    def tearDown(self) -> None:
        module._operation = self.original_operation
        module._safe_edit = self.original_safe_edit
        module.console_operation_text = self.original_operation_text
        module.console_operation_keyboard = self.original_operation_keyboard
        module.console_operation_finished = self.original_operation_finished

    async def test_unexpected_watcher_failure_is_logged_and_isolated(self) -> None:
        error = RuntimeError("telegram render failed")

        async def operation(client, operation_id):
            return {"id": operation_id}

        async def fail_edit(*args, **kwargs):
            raise error

        module._operation = operation
        module._safe_edit = fail_edit

        with self.assertLogs(module.logger, level="ERROR") as captured:
            await module._watch_console_operation(
                object(),
                object(),
                "op-41",
                bot=object(),
                recipient_id=17,
            )

        rendered = "\n".join(captured.output)
        self.assertIn("Supervisor console watcher failed", rendered)
        self.assertIn("operation=op-41", rendered)
        self.assertIn("recipient=17", rendered)
        self.assertIn("telegram render failed", rendered)

    async def test_watcher_cancellation_is_not_swallowed(self) -> None:
        async def cancel_operation(client, operation_id):
            raise asyncio.CancelledError

        module._operation = cancel_operation

        with self.assertRaises(asyncio.CancelledError):
            await module._watch_console_operation(
                object(),
                object(),
                "op-42",
                bot=object(),
                recipient_id=18,
            )


if __name__ == "__main__":
    unittest.main()
