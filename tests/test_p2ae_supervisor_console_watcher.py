from __future__ import annotations

import asyncio
import unittest

import velvet_bot.presentation.telegram.routers.supervisor.console as module


class _RecordingBot:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.documents: list[dict[str, object]] = []

    async def send_message(self, **kwargs: object) -> None:
        self.messages.append(dict(kwargs))

    async def send_document(self, **kwargs: object) -> None:
        self.documents.append(dict(kwargs))


class SupervisorConsoleResultDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_finished_short_result_does_not_send_duplicate_text_summary(self) -> None:
        bot = _RecordingBot()
        operation = {
            "id": "short-result",
            "status": "success",
            "result": {
                "title": "Ollama: список моделей",
                "returncode": 0,
                "output": "qwen3-vl:8b",
            },
        }

        await module._notify_console_result(bot, 17, operation)  # type: ignore[arg-type]

        self.assertEqual([], bot.messages)
        self.assertEqual([], bot.documents)

    async def test_finished_long_result_sends_only_full_output_attachment(self) -> None:
        bot = _RecordingBot()
        operation = {
            "id": "long-result",
            "status": "success",
            "result": {
                "title": "Запустить тесты проекта",
                "returncode": 0,
                "output": "x" * 3000,
            },
        }

        await module._notify_console_result(bot, 17, operation)  # type: ignore[arg-type]

        self.assertEqual([], bot.messages)
        self.assertEqual(1, len(bot.documents))
        self.assertEqual(17, bot.documents[0]["chat_id"])


class SupervisorConsoleWatcherBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.original_operation = module._operation
        self.original_edit_supervisor_message = module.edit_supervisor_message
        self.original_operation_text = module.console_operation_text
        self.original_operation_keyboard = module.console_operation_keyboard
        self.original_operation_finished = module.console_operation_finished

        module.console_operation_text = lambda operation: "rendered"
        module.console_operation_keyboard = lambda operation_id, **kwargs: "keyboard"
        module.console_operation_finished = lambda operation: False

    def tearDown(self) -> None:
        module._operation = self.original_operation
        module.edit_supervisor_message = self.original_edit_supervisor_message
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
        module.edit_supervisor_message = fail_edit

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
