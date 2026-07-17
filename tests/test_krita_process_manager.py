from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from velvet_supervisor.krita_process import KritaProcessManager


class _FakeProcess:
    def __init__(self, pid: int = 4242) -> None:
        self.pid = pid
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


class KritaProcessManagerTests(unittest.TestCase):
    def _manager(self, root: Path) -> KritaProcessManager:
        project = root / "project"
        runtime = project / "runtime"
        bridge = root / "bridge"
        executable = root / "krita.exe"
        executable.write_bytes(b"exe")
        (project / "tools" / "krita" / "velvet_logo").mkdir(parents=True)
        (project / "tools" / "krita" / "velvet_logo.desktop").write_text(
            "[Desktop Entry]",
            encoding="utf-8",
        )
        (project / "tools" / "krita" / "velvet_logo" / "__init__.py").write_text(
            "",
            encoding="utf-8",
        )
        environment = {
            "KRITA_AUTOSTART_ENABLED": "true",
            "KRITA_EXECUTABLE": str(executable),
            "KRITA_BRIDGE_DIR": str(bridge),
            "KRITA_IDLE_TIMEOUT_SECONDS": "600",
            "KRITA_PLUGIN_DIR": str(root / "plugin"),
        }
        with patch.dict("os.environ", environment, clear=False):
            return KritaProcessManager(project_dir=project, runtime_dir=runtime)

    def test_ensure_starts_managed_process_and_stop_terminates_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(Path(directory))
            process = _FakeProcess()
            with patch(
                "velvet_supervisor.krita_process.subprocess.Popen",
                return_value=process,
            ):
                status = manager.ensure()
            self.assertTrue(status["running"])
            self.assertTrue(status["managed"])
            self.assertEqual(status["pid"], process.pid)

            stopped = manager.stop()
            self.assertTrue(stopped["stopped"])
            self.assertTrue(process.terminated)

    def test_external_krita_is_used_but_never_owned_or_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(Path(directory))
            manager._running_krita_pids = lambda: {7777}  # type: ignore[method-assign]

            status = manager.ensure()
            self.assertTrue(status["running"])
            self.assertFalse(status["managed"])
            self.assertEqual(status["pid"], 7777)

            stopped = manager.stop()
            self.assertFalse(stopped["stopped"])
            self.assertFalse(stopped["managed"])

    def test_busy_bridge_defers_idle_stop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = self._manager(Path(directory))
            process = _FakeProcess()
            with patch(
                "velvet_supervisor.krita_process.subprocess.Popen",
                return_value=process,
            ):
                manager.ensure()
            requests = manager.bridge_dir / "requests"
            requests.mkdir(parents=True, exist_ok=True)
            (requests / "job-1.processing").write_text("{}", encoding="utf-8")
            manager._last_used_monotonic = time.monotonic() - 1_000

            stopped = manager.stop()
            self.assertFalse(stopped["stopped"])
            self.assertTrue(stopped["deferred"])
            self.assertFalse(process.terminated)


if __name__ == "__main__":
    unittest.main()
