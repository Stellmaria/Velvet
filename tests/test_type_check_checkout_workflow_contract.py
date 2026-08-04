from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "type-check.yml"
SCRIPT = ROOT / "scripts" / "ci_changed_surfaces.py"


def load_surface_module():
    spec = importlib.util.spec_from_file_location("ci_changed_surfaces_contract", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load ci_changed_surfaces")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_surface_module()


class TypeCheckCheckoutWorkflowContractTests(unittest.TestCase):
    def test_surface_detection_uses_shallow_exact_commits(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Checkout exact change head", source)
        self.assertIn("fetch-depth: 1", source)
        self.assertNotIn("fetch-depth: 0", source)
        self.assertIn("Fetch exact pull request base", source)
        self.assertIn('git fetch --no-tags --depth=1 origin "$BASE_SHA"', source)

    def test_exact_event_base_sha_is_preferred_without_history_fetch(self) -> None:
        base_sha = "a" * 40
        with patch.object(MODULE, "_ensure_commit") as ensure_commit, patch.object(
            MODULE.subprocess,
            "run",
        ) as run, patch.object(MODULE, "_git") as git:
            resolved = MODULE._resolve_pull_request_base(
                base_sha=base_sha,
                base_ref="main",
            )

        self.assertEqual(base_sha, resolved)
        ensure_commit.assert_called_once_with(base_sha)
        run.assert_not_called()
        git.assert_not_called()


if __name__ == "__main__":
    unittest.main()
