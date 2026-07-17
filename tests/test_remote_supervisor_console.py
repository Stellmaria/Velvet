from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from velvet_bot.presentation.telegram.supervisor.remote_views import (
    console_keyboard,
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

    def test_unknown_and_shell_syntax_are_rejected(self) -> None:
        for value in (
            "whoami",
            "git status & shutdown /s",
            "git status | more",
            "git status > result.txt",
            "powershell -EncodedCommand AAAA",
            "git status; taskkill /f /im python.exe",
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
