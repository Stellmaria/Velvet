from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci_changed_surfaces.py"
SECURITY_WORKFLOW = ROOT / ".github" / "workflows" / "security.yml"
TYPE_WORKFLOW = ROOT / ".github" / "workflows" / "type-check.yml"
NOTES_WORKFLOW = ROOT / ".github" / "workflows" / "project-notes-contract.yml"


def load_module():
    spec = importlib.util.spec_from_file_location("ci_changed_surfaces", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load ci_changed_surfaces")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module()


class CiChangedSurfacesTests(unittest.TestCase):
    def test_docs_only_change_keeps_heavy_surfaces_disabled(self) -> None:
        outputs = MODULE.classify_paths(
            ["docs/worklog/2026-08-04-ci-optimization.md", "README.md"]
        )
        self.assertFalse(any(outputs.values()))

    def test_workflow_change_runs_supply_chain_and_actions_codeql(self) -> None:
        outputs = MODULE.classify_paths([".github/workflows/security.yml"])
        self.assertTrue(outputs["supply_chain"])
        self.assertTrue(outputs["codeql_actions"])
        self.assertFalse(outputs["codeql_python"])
        self.assertTrue(outputs["image"])

    def test_python_change_selects_python_scanners(self) -> None:
        outputs = MODULE.classify_paths(["velvet_bot/topics.py"])
        self.assertTrue(outputs["static_tools"])
        self.assertTrue(outputs["codeql_python"])
        self.assertTrue(outputs["image"])
        self.assertTrue(outputs["mypy"])

    def test_unbounded_python_change_does_not_run_mypy(self) -> None:
        outputs = MODULE.classify_paths(["scripts/check_project_notes.py"])
        self.assertTrue(outputs["static_tools"])
        self.assertTrue(outputs["codeql_python"])
        self.assertFalse(outputs["mypy"])

    def test_dependency_change_runs_all_dependency_checks(self) -> None:
        outputs = MODULE.classify_paths(["requirements.lock"])
        self.assertTrue(outputs["supply_chain"])
        self.assertTrue(outputs["dependency_audit"])
        self.assertTrue(outputs["image"])

    def test_full_scan_enables_every_surface(self) -> None:
        outputs = MODULE.classify_paths([], full_scan=True)
        self.assertTrue(outputs)
        self.assertTrue(all(outputs.values()))

    def test_outputs_use_github_boolean_spelling(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "github-output.txt"
            MODULE.write_outputs(
                output,
                {"alpha": True, "beta": False},
                full_scan=False,
            )
            self.assertEqual(
                "full_scan=false\nalpha=true\nbeta=false\n",
                output.read_text(encoding="utf-8"),
            )

    def test_security_workflow_parallelizes_and_keeps_daily_full_scan(self) -> None:
        source = SECURITY_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('cron: "23 3 * * *"', source)
        self.assertNotIn("needs:", source)
        self.assertGreaterEqual(source.count("scripts/ci_changed_surfaces.py"), 4)
        self.assertIn("--cache-from type=gha,scope=velvet-production-image", source)
        self.assertIn("Skip unchanged CodeQL surface", source)

    def test_type_check_preserves_status_with_a_fast_path(self) -> None:
        source = TYPE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Resolve changed mypy surface", source)
        self.assertIn("steps.changes.outputs.mypy == 'true'", source)
        self.assertIn("Skip unchanged bounded type surface", source)

    def test_project_notes_fetches_exact_base_without_obsolete_setup(self) -> None:
        source = NOTES_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("cancel-in-progress: true", source)
        self.assertIn("fetch-depth: 0", source)
        self.assertNotIn("fetch-depth: 2", source)
        self.assertNotIn("actions/setup-python", source)
        self.assertNotIn("git fetch", source)
        self.assertIn("github.event.pull_request.base.sha", source)


if __name__ == "__main__":
    unittest.main()
