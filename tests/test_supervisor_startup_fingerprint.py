from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest.mock import patch

from velvet_supervisor.runtime import _startup_identity


ROOT = Path(__file__).resolve().parents[1]


class _Repository:
    def __init__(self, head: str = "890005f76bfb163f") -> None:
        self.head = head

    def head_sha(self) -> str:
        return self.head


class _BrokenRepository:
    def head_sha(self) -> str:
        raise RuntimeError("git unavailable")


class SupervisorStartupFingerprintTests(unittest.TestCase):
    def test_identity_contains_project_head_and_unicode_contract(self) -> None:
        with patch.dict(
            os.environ,
            {"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
            clear=True,
        ):
            rendered = _startup_identity(Path(r"E:\python\main\velevt"), _Repository())

        self.assertIn(r"Проект: E:\python\main\velevt", rendered)
        self.assertIn("Git HEAD: 890005f76bfb", rendered)
        self.assertIn("PYTHONUTF8: 1", rendered)
        self.assertIn("PYTHONIOENCODING: utf-8", rendered)

    def test_identity_reports_git_failure_without_breaking_startup(self) -> None:
        rendered = _startup_identity(Path("project"), _BrokenRepository())
        self.assertIn("Git HEAD: unavailable:RuntimeError", rendered)

    def test_run_script_forces_utf8_before_starting_python(self) -> None:
        source = (ROOT / "scripts/run_supervisor.ps1").read_text(encoding="utf-8")
        utf8_position = source.index('$env:PYTHONUTF8 = "1"')
        start_position = source.index("& $PythonExe -m velvet_supervisor")
        self.assertLess(utf8_position, start_position)
        self.assertIn('$env:PYTHONIOENCODING = "utf-8"', source)

    def test_refresh_script_is_safe_and_restarts_stale_processes(self) -> None:
        source = (ROOT / "scripts/refresh_supervisor.ps1").read_text(encoding="utf-8")
        required = (
            "git status --porcelain",
            "git merge-base --is-ancestor HEAD origin/main",
            "schtasks.exe /End",
            "Get-CimInstance Win32_Process",
            "Stop-Process",
            "git pull --ff-only origin main",
            "register_supervisor_task.ps1",
        )
        for marker in required:
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()
