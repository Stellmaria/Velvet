from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from velvet_bot.presentation.telegram.supervisor.remote_views import (
    console_keyboard,
    console_text,
    operation_history_text,
    self_control_keyboard,
)
from velvet_bot.presentation.telegram.supervisor.views import _main_keyboard
from velvet_supervisor.remote_console import (
    RemoteCommandFailed,
    RemoteCommandRegistry,
    RemoteCommandRejected,
)


class RemoteConsoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.project_dir = Path(self.temp_dir.name)
        self.settings = SimpleNamespace(
            project_dir=self.project_dir,
            python_executable="python.exe",
            test_command=("python.exe", "-m", "unittest", "discover", "-s", "tests", "-v"),
            command_timeout_seconds=900,
            api_token="supervisor-secret-token-123456",
            notification_bot_token="123456789:abcdefghijklmnopqrstuvwxyzABCDE",
        )
        self.registry = RemoteCommandRegistry(self.settings)  # type: ignore[arg-type]

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_exact_alias_resolves_to_fixed_argv(self) -> None:
        spec = self.registry.resolve("git status --short")
        self.assertEqual("git-status", spec.key)
        self.assertEqual(("git", "status", "--short"), spec.command)

    def test_recovery_commands_resolve_to_fixed_argv(self) -> None:
        expected = {
            "git clean -nd": ("git-clean-preview", ("git", "clean", "-nd")),
            "аварийный stash": (
                "git-stash-save-all",
                (
                    "git",
                    "stash",
                    "push",
                    "--include-untracked",
                    "-m",
                    "Supervisor emergency stash",
                ),
            ),
            "git stash pop": ("git-stash-pop", ("git", "stash", "pop")),
            "git rev-list --left-right --count HEAD...origin/main": (
                "git-sync-count",
                ("git", "rev-list", "--left-right", "--count", "HEAD...origin/main"),
            ),
        }
        for alias, (key, command) in expected.items():
            with self.subTest(alias=alias):
                spec = self.registry.resolve(alias)
                self.assertEqual(key, spec.key)
                self.assertEqual(command, spec.command)

    def test_krita_cleanup_resolves_only_to_fixed_path(self) -> None:
        spec = self.registry.resolve(
            "git clean -f -- tools/krita/Velvet_Anatomy_Krita_Plugin_bridge.zip"
        )
        self.assertEqual("git-clean-krita-bridge", spec.key)
        self.assertEqual(
            (
                "git",
                "clean",
                "-f",
                "--",
                "tools/krita/Velvet_Anatomy_Krita_Plugin_bridge.zip",
            ),
            spec.command,
        )

    def test_catalog_contains_remote_recovery_toolkit(self) -> None:
        keys = {spec.key for spec in self.registry.catalog()}
        self.assertTrue(
            {
                "git-status",
                "git-branch",
                "git-fetch",
                "git-sync-count",
                "git-incoming",
                "git-outgoing",
                "git-clean-preview",
                "git-stash-list",
                "git-stash-save-all",
                "git-stash-show",
                "git-stash-pop",
                "git-clean-krita-bridge",
                "pip-check",
                "compile",
                "tests",
                "task-status",
                "python-processes",
                "network-config",
                "disk-volumes",
            }.issubset(keys)
        )

    def test_standard_menu_hides_legacy_and_emergency_commands(self) -> None:
        commands = [spec.to_dict() for spec in self.registry.catalog()]
        text = console_text(commands)

        self.assertIn("Ollama: восстановить набор моделей", text)
        self.assertIn("Git: получить origin", text)
        self.assertIn("Процессы Python", text)
        self.assertNotIn("Ollama: настроить набор моделей", text)
        self.assertNotIn("Ollama: установить набор моделей", text)
        self.assertNotIn("Ollama: проверить набор моделей", text)
        self.assertNotIn("Состояние задачи VelvetSupervisor", text)
        self.assertNotIn("Сетевые адреса компьютера", text)
        self.assertNotIn("Свободное место на дисках", text)
        self.assertNotIn("вернуть последний stash", text.casefold())
        self.assertIn("остаются в безопасном allowlist", text)

        # Hidden commands remain resolvable for an explicit emergency action.
        self.assertEqual("git-stash-pop", self.registry.resolve("git stash pop").key)
        self.assertEqual(
            "ollama-configure-qwen3-vl-4b",
            self.registry.resolve("ollama configure qwen3-vl 4b").key,
        )

    def test_operation_history_never_exceeds_safe_telegram_budget(self) -> None:
        operations = []
        for index in range(20):
            status = "error" if index == 0 else "success"
            operations.append(
                {
                    "id": f"operation-{index:02d}",
                    "kind": "console-command",
                    "status": status,
                    "message": "Команда принята: " + ("очень длинное описание " * 50),
                    "result": {
                        "output": f"begin-{index}\n" + ("x" * 6000) + f"\nend-{index}",
                    },
                    "error": ("ошибка " * 200) if status == "error" else "",
                }
            )

        text = operation_history_text(operations)

        self.assertLessEqual(len(text), 3600)
        self.assertIn("operation-00", text)
        self.assertIn("end-0", text)
        self.assertNotIn("begin-1", text)
        self.assertNotIn("end-1", text)
        self.assertIn("Не показано более старых операций", text)

    def test_unknown_and_shell_syntax_are_rejected(self) -> None:
        for value in (
            "whoami",
            "git status & shutdown /s",
            "git status | more",
            "git status > result.txt",
            "powershell -EncodedCommand AAAA",
            "git status; taskkill /f /im python.exe",
            "git clean -fd",
            "git clean -f -- another-file.zip",
            "git reset --hard origin/main",
            "git push --force",
            "del important.db",
        ):
            with self.subTest(value=value):
                with self.assertRaises(RemoteCommandRejected):
                    self.registry.resolve(value)

    def test_execute_never_uses_shell_and_redacts_secrets(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["git", "status", "--short"],
            returncode=0,
            stdout=(
                "SUPERVISOR_TOKEN=supervisor-secret-token-123456\n"
                "postgresql://velvet:secret@localhost:5432/velvet\n"
            ),
            stderr=None,
        )
        with patch("velvet_supervisor.remote_console.subprocess.run", return_value=completed) as run:
            result = self.registry.execute("git-status")

        kwargs = run.call_args.kwargs
        self.assertIs(kwargs["shell"], False)
        self.assertEqual(["git", "status", "--short"], run.call_args.args[0])
        self.assertEqual(str(self.project_dir), kwargs["cwd"])
        output = str(result["output"])
        self.assertNotIn("supervisor-secret-token", output)
        self.assertNotIn("secret@localhost", output)
        self.assertIn("redacted", output)

    def test_nonzero_exit_is_an_operation_error_with_result(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["ollama", "list"],
            returncode=1,
            stdout="ollama is unavailable",
            stderr=None,
        )
        with patch("velvet_supervisor.remote_console.subprocess.run", return_value=completed):
            with self.assertRaises(RemoteCommandFailed) as context:
                self.registry.execute("ollama-list")
        self.assertEqual(1, context.exception.result["returncode"])
        self.assertIn("unavailable", str(context.exception.result["output"]))

    def test_menu_exposes_console_and_self_control(self) -> None:
        callbacks = [
            button.callback_data
            for row in _main_keyboard().inline_keyboard
            for button in row
            if button.callback_data
        ]
        self.assertTrue(any("console.menu" in value for value in callbacks))
        self.assertTrue(any("self.menu" in value for value in callbacks))

    def test_all_remote_control_callbacks_fit_telegram_limit(self) -> None:
        commands = [spec.to_dict() for spec in self.registry.catalog()]
        markups = (console_keyboard(commands), self_control_keyboard())
        for markup in markups:
            for row in markup.inline_keyboard:
                for button in row:
                    if button.callback_data:
                        self.assertLessEqual(len(button.callback_data.encode("utf-8")), 64)


if __name__ == "__main__":
    unittest.main()
