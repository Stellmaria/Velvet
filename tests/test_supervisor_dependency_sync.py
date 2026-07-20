from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from velvet_supervisor.dependencies import (
    DependencySyncError,
    sync_current_requirements,
    sync_remote_requirements,
)


class SupervisorDependencySyncTests(unittest.TestCase):
    def _settings(self, root: Path):
        return SimpleNamespace(
            project_dir=root,
            runtime_dir=root / "runtime" / "supervisor",
            python_executable=root / ".venv" / "Scripts" / "python.exe",
            command_timeout_seconds=900,
            update_remote="origin",
            update_branch="main",
        )

    def test_current_requirements_are_installed_once_and_cached(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text(
                "aiogram==3.29.1\ncryptography==49.0.0\n",
                encoding="utf-8",
            )
            settings = self._settings(root)
            completed = SimpleNamespace(returncode=0, stdout="installed")
            with patch(
                "velvet_supervisor.dependencies._run",
                return_value=completed,
            ) as runner:
                first = sync_current_requirements(settings)
                second = sync_current_requirements(settings)

            self.assertTrue(first.installed)
            self.assertFalse(second.installed)
            self.assertEqual(1, runner.call_count)
            command = runner.call_args.args[0]
            self.assertEqual("-m", command[1])
            self.assertEqual("pip", command[2])
            self.assertIn("cryptography==49.0.0", (settings.runtime_dir / "requirements-sync.txt").read_text())

    def test_remote_requirements_are_fetched_before_pip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = self._settings(root)
            calls: list[tuple[str, ...]] = []

            def fake_run(command, **kwargs):
                calls.append(tuple(command))
                if command[:2] == ("git", "show"):
                    return SimpleNamespace(
                        returncode=0,
                        stdout="cryptography==49.0.0\n",
                    )
                return SimpleNamespace(returncode=0, stdout="ok")

            with patch("velvet_supervisor.dependencies._run", side_effect=fake_run):
                result = sync_remote_requirements(settings)

            self.assertTrue(result.installed)
            self.assertEqual(("git", "fetch", "--prune", "origin", "main"), calls[0])
            self.assertEqual(("git", "show", "origin/main:requirements.txt"), calls[1])
            self.assertEqual("pip", calls[2][2])

    def test_failed_pip_does_not_write_success_cache(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "requirements.txt").write_text(
                "cryptography==49.0.0\n",
                encoding="utf-8",
            )
            settings = self._settings(root)
            with patch(
                "velvet_supervisor.dependencies._run",
                return_value=SimpleNamespace(returncode=1, stdout="network unavailable"),
            ):
                with self.assertRaisesRegex(DependencySyncError, "network unavailable"):
                    sync_current_requirements(settings)

            self.assertFalse((settings.runtime_dir / "requirements-sync.sha256").exists())


if __name__ == "__main__":
    unittest.main()
