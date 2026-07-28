from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from velvet_supervisor.instance_guard import (
    SupervisorAlreadyRunning,
    SupervisorInstanceGuard,
)


class SupervisorInstanceGuardTests(unittest.TestCase):
    def test_instance_guard_rejects_second_live_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "supervisor.instance.lock"
            first = SupervisorInstanceGuard(path, pid=os.getpid())
            first.acquire()
            self.addCleanup(first.release)

            second = SupervisorInstanceGuard(path, pid=os.getpid() + 100_000)
            with self.assertRaisesRegex(SupervisorAlreadyRunning, "уже запущен"):
                second.acquire()

            first.release()
            self.assertFalse(path.exists())

    def test_instance_guard_replaces_stale_owner(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "supervisor.instance.lock"
            path.write_text(json.dumps({"pid": 987_654_321}), encoding="utf-8")

            with patch(
                "velvet_supervisor.instance_guard._pid_is_alive",
                return_value=False,
            ):
                guard = SupervisorInstanceGuard(path, pid=4321)
                guard.acquire()

            self.assertEqual(
                4321,
                json.loads(path.read_text(encoding="utf-8"))["pid"],
            )
            guard.release()
            self.assertFalse(path.exists())

    def test_instance_guard_does_not_remove_foreign_lock_on_release(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "supervisor.instance.lock"
            guard = SupervisorInstanceGuard(path, pid=1234)
            guard.acquire()
            path.write_text(json.dumps({"pid": 5678}), encoding="utf-8")

            guard.release()

            self.assertTrue(path.exists())
            self.assertEqual(
                5678,
                json.loads(path.read_text(encoding="utf-8"))["pid"],
            )


if __name__ == "__main__":
    unittest.main()
