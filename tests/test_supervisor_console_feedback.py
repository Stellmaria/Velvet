from __future__ import annotations

import unittest

from velvet_bot.presentation.telegram.supervisor.console_results import (
    console_operation_dm_text,
    console_operation_finished,
    console_operation_output_attachment,
    console_operation_text,
)


class SupervisorConsoleFeedbackTests(unittest.TestCase):
    def test_running_operation_promises_automatic_update(self) -> None:
        operation = {
            "id": "abc123",
            "kind": "console-command",
            "status": "running",
            "message": "Команда принята: Git status",
            "result": {},
        }

        text = console_operation_text(operation)

        self.assertIn("⚙️ выполняется", text)
        self.assertIn("обновится автоматически", text)
        self.assertFalse(console_operation_finished(operation))

    def test_success_result_contains_returncode_duration_and_output(self) -> None:
        operation = {
            "id": "abc123",
            "kind": "console-command",
            "status": "success",
            "message": "Команда принята: Git status",
            "result": {
                "title": "Git: локальные изменения",
                "command": "git status --short",
                "returncode": 0,
                "duration_seconds": 0.321,
                "output": " M velvet_bot/example.py",
            },
        }

        text = console_operation_text(operation)

        self.assertIn("✅ завершено", text)
        self.assertIn("Код возврата: <b>0</b>", text)
        self.assertIn("0.321 сек.", text)
        self.assertIn("git status --short", text)
        self.assertIn("velvet_bot/example.py", text)
        self.assertTrue(console_operation_finished(operation))

    def test_success_without_output_is_explained(self) -> None:
        operation = {
            "id": "compile1",
            "status": "success",
            "message": "Команда принята: Проверить синтаксис проекта",
            "result": {
                "title": "Проверить синтаксис проекта",
                "command": "python -m compileall -q velvet_bot",
                "returncode": 0,
                "duration_seconds": 1.4,
                "output": "",
            },
        }

        text = console_operation_text(operation)

        self.assertIn("успешно без текстового вывода", text)

    def test_error_result_contains_failure_details(self) -> None:
        operation = {
            "id": "failed1",
            "status": "error",
            "message": "Команда принята: Тесты",
            "result": {
                "title": "Запустить тесты проекта",
                "command": "python -m unittest discover -s tests -v",
                "returncode": 1,
                "duration_seconds": 9.7,
                "output": "FAILED (failures=1)",
            },
            "error": "Команда завершилась с кодом 1.",
        }

        text = console_operation_text(operation)

        self.assertIn("❌ ошибка", text)
        self.assertIn("Код возврата: <b>1</b>", text)
        self.assertIn("FAILED (failures=1)", text)
        self.assertIn("Команда завершилась с кодом 1.", text)
        self.assertTrue(console_operation_finished(operation))

    def test_long_output_is_truncated_from_the_start(self) -> None:
        output = "begin-marker\n" + ("x" * 3000) + "\nend-marker"
        operation = {
            "id": "long1",
            "status": "success",
            "result": {
                "title": "Long output",
                "returncode": 0,
                "duration_seconds": 1,
                "output": output,
            },
        }

        text = console_operation_text(operation)

        self.assertNotIn("begin-marker", text)
        self.assertIn("end-marker", text)
        self.assertIn("Показан конец длинного вывода", text)
        self.assertIn("приложен файлом в ЛС", text)

    def test_dm_result_uses_explicit_notification_heading(self) -> None:
        operation = {
            "id": "dm1",
            "status": "success",
            "result": {
                "title": "Git status",
                "returncode": 0,
                "duration_seconds": 0.1,
                "output": "clean",
            },
        }

        text = console_operation_dm_text(operation)

        self.assertIn("📬 Итог команды Supervisor", text)
        self.assertNotIn("🖥 Команда Supervisor", text)

    def test_short_output_does_not_create_attachment(self) -> None:
        operation = {
            "id": "short1",
            "status": "success",
            "result": {"output": "short output"},
        }

        self.assertIsNone(console_operation_output_attachment(operation))

    def test_long_output_attachment_contains_complete_utf8_result(self) -> None:
        output = "начало\n" + ("x" * 3000) + "\nконец"
        operation = {
            "id": "long/result:1",
            "status": "error",
            "result": {
                "title": "Полные тесты",
                "command": "python -m unittest discover -s tests -v",
                "returncode": 1,
                "duration_seconds": 12.5,
                "output": output,
            },
            "error": "Команда завершилась с кодом 1.",
        }

        attachment = console_operation_output_attachment(operation)

        self.assertIsNotNone(attachment)
        assert attachment is not None
        filename, payload = attachment
        decoded = payload.decode("utf-8")
        self.assertEqual(filename, "supervisor-console-longresult1.txt")
        self.assertIn("начало", decoded)
        self.assertIn("конец", decoded)
        self.assertIn("Return code: 1", decoded)
        self.assertIn("Команда завершилась с кодом 1.", decoded)


if __name__ == "__main__":
    unittest.main()
