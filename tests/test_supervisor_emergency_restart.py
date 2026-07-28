from __future__ import annotations

import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from velvet_supervisor.runtime import OperationConflict
from velvet_supervisor.runtime_extended import VelvetSupervisor


class _Process:
    pid = 4321

    @staticmethod
    def poll():
        return None


class SupervisorEmergencyRestartTests(unittest.TestCase):
    def setUp(self) -> None:
        runtime = object.__new__(VelvetSupervisor)
        runtime.settings = SimpleNamespace(project_dir=".")
        runtime._operation_lock = threading.Lock()
        runtime._operation_lock.acquire()
        runtime._lock = threading.RLock()
        runtime._process = _Process()
        runtime._last_operation = None
        runtime._persisted = []
        runtime._persist_operation = runtime._persisted.append
        self.runtime = runtime

    def tearDown(self) -> None:
        if self.runtime._operation_lock.locked():
            self.runtime._operation_lock.release()

    def test_plain_self_restart_bypasses_stuck_operation_lock(self) -> None:
        launch = SimpleNamespace(to_dict=lambda: {"task_name": "VelvetSupervisorBootstrap-test"})
        with patch(
            "velvet_supervisor.runtime_extended.launch_bootstrap_short",
            return_value=launch,
        ) as helper:
            operation = self.runtime.schedule_supervisor_restart(update=False)

        self.assertEqual("supervisor-restart", operation.kind)
        self.assertEqual("handed-off", operation.status)
        self.assertIn("Аварийный перезапуск", operation.message)
        self.assertTrue(self.runtime._operation_lock.locked())
        helper.assert_called_once()
        self.assertEqual("restart", helper.call_args.kwargs["action"])
        self.assertEqual(4321, helper.call_args.kwargs["bot_pid"])

    def test_self_update_still_rejects_stuck_operation_lock(self) -> None:
        with self.assertRaisesRegex(OperationConflict, "другая системная операция"):
            self.runtime.schedule_supervisor_restart(update=True)


if __name__ == "__main__":
    unittest.main()
