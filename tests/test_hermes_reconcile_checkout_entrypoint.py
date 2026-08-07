from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "deploy/hermes-reconcile/host_reconcile_entrypoint.py"
INSTALLER = ROOT / "deploy/hermes-reconcile/install.sh"
UNIT = ROOT / "deploy/systemd/hermes-operator-reconcile.service"


def load_entrypoint():
    spec = importlib.util.spec_from_file_location(
        "host_reconcile_entrypoint_under_test",
        ENTRYPOINT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeRuntime:
    def __init__(self, app_dir: str) -> None:
        self.app_dir = Path(app_dir).resolve()
        self.branch = "main"

    def _run(self, command, *, timeout, check=True):
        raise AssertionError(f"unexpected command: {command}")


class HermesReconcileCheckoutEntrypointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entrypoint = load_entrypoint()

    def patched_runtime(self, app_dir: str):
        host = SimpleNamespace(ReconcileRuntime=FakeRuntime)
        self.entrypoint._patch_runtime(host)
        return host.ReconcileRuntime(app_dir)

    def test_detached_checkout_is_allowed_only_at_clean_fetched_origin_main(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.patched_runtime(temporary)
            runtime._git_process = mock.Mock(
                return_value=subprocess.CompletedProcess([], 1, "", "")
            )
            runtime._git = mock.Mock(
                side_effect=[temporary, "", "abc123", "abc123"]
            )

            self.assertEqual(runtime._verify_checkout(), "abc123")
            runtime._git_process.assert_called_once_with(
                "symbolic-ref",
                "--short",
                "HEAD",
                check=False,
            )

    def test_detached_checkout_is_rejected_when_head_differs_from_origin_main(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.patched_runtime(temporary)
            runtime._git_process = mock.Mock(
                return_value=subprocess.CompletedProcess([], 1, "", "")
            )
            runtime._git = mock.Mock(
                side_effect=[temporary, "", "old", "new"]
            )

            with self.assertRaisesRegex(RuntimeError, "does not match"):
                runtime._verify_checkout()

    def test_attached_checkout_on_unexpected_branch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.patched_runtime(temporary)
            runtime._git_process = mock.Mock(
                return_value=subprocess.CompletedProcess([], 0, "release\n", "")
            )
            runtime._git = mock.Mock(return_value=temporary)

            with self.assertRaisesRegex(RuntimeError, "got release"):
                runtime._verify_checkout()

    def test_git_commands_pin_safe_directory_and_disable_optional_locks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            runtime = self.patched_runtime(temporary)
            runtime._run = mock.Mock(
                return_value=subprocess.CompletedProcess([], 0, "abc\n", "")
            )

            self.assertEqual(runtime._git("rev-parse", "HEAD"), "abc")
            command = runtime._run.call_args.args[0]
            self.assertEqual(
                command[0:4],
                [
                    "/usr/bin/git",
                    "--no-optional-locks",
                    "-c",
                    f"safe.directory={runtime.app_dir}",
                ],
            )
            self.assertNotIn("safe.directory=*", command)

    def test_entrypoint_is_installed_root_owned_and_used_by_systemd(self) -> None:
        installer = INSTALLER.read_text(encoding="utf-8")
        unit = UNIT.read_text(encoding="utf-8")
        target = "/usr/local/libexec/velvet-hermes-operator-reconcile-entrypoint.py"
        self.assertIn(f'HOST_ENTRYPOINT_TARGET="{target}"', installer)
        self.assertIn(
            'install -m 0755 -o root -g root "$SOURCE_DIR/host_reconcile_entrypoint.py" "$HOST_ENTRYPOINT_TARGET"',
            installer,
        )
        self.assertIn(f"ExecStart=/usr/bin/python3 {target}", unit)
        self.assertNotIn(
            "ExecStart=/usr/bin/python3 /srv/velvet/deploy/hermes-reconcile/host_reconcile_entrypoint.py",
            unit,
        )

    def test_private_tmp_keeps_docker_bind_sources_host_visible(self) -> None:
        entrypoint = ENTRYPOINT.read_text(encoding="utf-8")
        unit = UNIT.read_text(encoding="utf-8")

        self.assertIn('self.reconcile_tmp_dir = Path(state_dir) / "tmp"', entrypoint)
        self.assertIn('env["TMPDIR"] = str(reconcile_tmp_dir)', entrypoint)
        self.assertIn("PrivateTmp=true", unit)
        read_write_line = next(
            line for line in unit.splitlines() if line.startswith("ReadWritePaths=")
        )
        self.assertIn(
            "/srv/hermes-operator-control/reconcile-state",
            read_write_line.split(),
        )


if __name__ == "__main__":
    unittest.main()
