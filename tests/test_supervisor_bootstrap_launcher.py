from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from velvet_supervisor.bootstrap_launcher import launch_bootstrap_short


class SupervisorBootstrapLauncherTests(unittest.TestCase):
    def test_task_action_stays_below_windows_tr_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "a-very-long-project-directory" / "velvet"
            runtime = project / "runtime" / "supervisor"
            project.mkdir(parents=True)
            settings = SimpleNamespace(
                project_dir=project,
                runtime_dir=runtime,
                python_executable=str(project / ".venv" / "Scripts" / "python.exe"),
            )

            with (
                patch("velvet_supervisor.bootstrap_launcher.os.name", "nt"),
                patch("velvet_supervisor.bootstrap_launcher._acquire_lock"),
                patch("velvet_supervisor.bootstrap_launcher._release_lock"),
                patch("velvet_supervisor.bootstrap_launcher._delete_task"),
                patch("velvet_supervisor.bootstrap_launcher._run") as run,
            ):
                launch = launch_bootstrap_short(
                    settings,
                    action="restart",
                    operation_id="abcdef123456",
                    supervisor_pid=123,
                    bot_pid=456,
                )

            create_command = run.call_args_list[0].args[0]
            action_index = create_command.index("/TR") + 1
            task_action = create_command[action_index]
            self.assertLessEqual(len(task_action), 240)
            self.assertIn("cmd.exe", task_action.casefold())

            wrappers = list(runtime.glob("bootstrap-*.cmd"))
            self.assertEqual(len(wrappers), 1)
            wrapper_text = wrappers[0].read_text(encoding="utf-8")
            self.assertIn("--project-dir", wrapper_text)
            self.assertIn(str(project), wrapper_text)
            self.assertIn("--supervisor-pid 123", wrapper_text)
            self.assertEqual(launch.task_name, "VelvetSupervisorBootstrap-abcdef123456")


if __name__ == "__main__":
    unittest.main()
