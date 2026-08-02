from __future__ import annotations

import ast
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


reconcile = load_module(
    "hermes_coder_reconcile_test_module",
    ROOT / "deploy/hermes-coders/reconcile_workspaces.py",
)


class HermesCoderRuntimeContractTests(unittest.TestCase):
    def test_runtime_override_bypasses_s6_and_exposes_git_config(self) -> None:
        source = (ROOT / "deploy/hermes-coders/compose.runtime.yaml").read_text(
            encoding="utf-8"
        )
        self.assertEqual(2, source.count("GIT_CONFIG_GLOBAL: /opt/data/.gitconfig"))
        self.assertEqual(2, source.count("- /app/codex_routed_runner.py"))
        self.assertEqual(2, source.count("command: []"))
        self.assertNotIn("/init", source)

    def test_systemd_uses_override_reconcile_and_smoke(self) -> None:
        source = (ROOT / "deploy/systemd/hermes-coders.service").read_text(
            encoding="utf-8"
        )
        compose_lines = [line for line in source.splitlines() if "docker compose" in line]
        self.assertEqual(4, len(compose_lines))
        for line in compose_lines:
            self.assertIn("-f compose.yaml -f compose.runtime.yaml", line)
        reconcile_line = (
            "ExecStartPre=+/usr/bin/python3 "
            "/srv/velvet/deploy/hermes-coders/reconcile_workspaces.py"
        )
        self.assertIn(reconcile_line, source)
        self.assertLess(source.index(reconcile_line), source.index("preflight.py"))
        self.assertIn("ExecStartPost=/usr/bin/python3", source)
        self.assertIn("runtime_smoke.py", source)

    def test_reconcile_source_is_fixed_scope_and_parses(self) -> None:
        path = ROOT / "deploy/hermes-coders/reconcile_workspaces.py"
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        self.assertIn("workspaces/velvet", source)
        self.assertIn("workspaces/max", source)
        self.assertIn("workspaces/velvet-codex", source)
        self.assertIn("workspaces/max-codex", source)
        self.assertIn("https://github.com/Stellmaria/Velvet.git", source)
        self.assertIn(
            "https://github.com/Stellmaria/romatic_club_bot_max.git",
            source,
        )
        self.assertNotIn("git@github.com:", source)


class WorkspaceReconcileTests(unittest.TestCase):
    def setUp(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git is unavailable")

    def _init_workspace(self, root: Path, relative_path: str, origin: str) -> Path:
        target = root / relative_path
        target.mkdir(parents=True)
        subprocess.run(
            ["git", "init", "--quiet", str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            ["git", "-C", str(target), "remote", "add", "origin", origin],
            check=True,
            capture_output=True,
            text=True,
        )
        return target

    def test_reconcile_normalizes_all_origins_to_https(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for workspace in reconcile.WORKSPACES:
                self._init_workspace(
                    root,
                    workspace.relative_path,
                    "git@github.com:Stellmaria/wrong.git",
                )
                reconcile.reconcile_workspace(
                    root,
                    workspace,
                    os.getuid(),
                    os.getgid(),
                )

            for workspace in reconcile.WORKSPACES:
                target = root / workspace.relative_path
                result = subprocess.run(
                    ["git", "-C", str(target), "remote", "get-url", "origin"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(workspace.origin, result.stdout.strip())

    def test_reconcile_repairs_ownership_before_git(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workspace = reconcile.WORKSPACES[0]
            target = self._init_workspace(root, workspace.relative_path, workspace.origin)
            with (
                patch.object(reconcile, "ownership_needs_repair", return_value=True),
                patch.object(reconcile, "chown_tree") as chown_tree,
            ):
                reconcile.reconcile_workspace(
                    root,
                    workspace,
                    os.getuid(),
                    os.getgid(),
                )
            chown_tree.assert_called_once_with(target, os.getuid(), os.getgid())

    def test_main_rejects_non_root_execution(self) -> None:
        with patch.object(reconcile.os, "geteuid", return_value=1000):
            self.assertEqual(1, reconcile.main())


if __name__ == "__main__":
    unittest.main()
