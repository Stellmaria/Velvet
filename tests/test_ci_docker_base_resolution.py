from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci_changed_surfaces.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ci_changed_surfaces_base", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load ci_changed_surfaces")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


class DockerBaseResolutionTests(unittest.TestCase):
    def test_current_base_ref_wins_over_stale_payload_sha(self) -> None:
        with patch.object(MODULE.subprocess, "run") as run, patch.object(
            MODULE,
            "_git",
            return_value="c" * 40,
        ), patch.object(MODULE, "_ensure_commit") as ensure_commit:
            resolved = MODULE._resolve_pull_request_base(
                base_sha="b" * 40,
                base_ref="main",
            )

        self.assertEqual("c" * 40, resolved)
        ensure_commit.assert_not_called()
        command = run.call_args.args[0]
        self.assertEqual("git", command[0])
        self.assertIn("main:refs/remotes/origin/main", command)


if __name__ == "__main__":
    unittest.main()
