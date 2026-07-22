from __future__ import annotations

import asyncio
import logging
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from velvet_bot import runtime_stability
from velvet_supervisor.codex import summarize_codex_failure
from velvet_supervisor.dependencies import sync_remote_requirements


class NetworkFailureHandlingTests(unittest.TestCase):
    def test_codex_403_is_actionable_and_does_not_include_html(self) -> None:
        message = summarize_codex_failure(
            RuntimeError(
                "unexpected status 403 Forbidden: <html><style>.data{color:red}</style>"
                ", url: https://chatgpt.com/backend-api/codex/responses, cf-ray: test"
            )
        )
        self.assertIn("403 Forbidden", message)
        self.assertIn("codex --login", message)
        self.assertNotIn("<html>", message)
        self.assertNotIn(".data{", message)

    def test_asyncpg_close_after_network_drop_is_recoverable(self) -> None:
        async def close() -> None:
            return None

        loop = asyncio.new_event_loop()
        try:
            task = loop.create_task(close(), name="close-test")
            loop.run_until_complete(task)
            fake = SimpleNamespace()
            fake.__repr__ = lambda self: "<Task coro=<Connection.close() done>>"
            context = {
                "message": "Task exception was never retrieved",
                "future": _FutureRepr(),
                "exception": ConnectionAbortedError(1236, "Подключение к сети было разорвано локальной системой"),
            }
            self.assertTrue(
                runtime_stability.is_recoverable_asyncio_connection_close_context(context)
            )
        finally:
            loop.close()

    def test_asyncio_log_record_is_filtered(self) -> None:
        record = logging.LogRecord(
            "asyncio",
            logging.ERROR,
            "test.py",
            1,
            "Task exception was never retrieved future=<Task coro=<Connection.close() done>> exception=ConnectionAbortedError: Подключение к сети было разорвано",
            (),
            None,
        )
        self.assertTrue(runtime_stability.is_recoverable_aiogram_polling_record(record))

    def test_remote_requirements_fetch_retries_transient_network_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = SimpleNamespace(
                project_dir=root,
                runtime_dir=root / "runtime",
                python_executable="python",
                command_timeout_seconds=30,
                update_remote="origin",
                update_branch="main",
            )
            calls = 0

            def fake_run(command, **kwargs):
                nonlocal calls
                if command[:2] == ("git", "fetch"):
                    calls += 1
                    if calls < 3:
                        return subprocess.CompletedProcess(
                            command, 1, stdout="Failed to connect to github.com"
                        )
                    return subprocess.CompletedProcess(command, 0, stdout="ok")
                if command[:2] == ("git", "show"):
                    return subprocess.CompletedProcess(
                        command, 0, stdout="aiogram==3.29.1\n"
                    )
                return subprocess.CompletedProcess(command, 0, stdout="installed")

            with patch("velvet_supervisor.dependencies._run", side_effect=fake_run), patch(
                "velvet_supervisor.dependencies.time.sleep"
            ):
                result = sync_remote_requirements(settings)

            self.assertEqual(3, calls)
            self.assertTrue(result.installed)


class _FutureRepr:
    def __repr__(self) -> str:
        return "<Task finished coro=<Connection.close() done>>"


if __name__ == "__main__":
    unittest.main()
