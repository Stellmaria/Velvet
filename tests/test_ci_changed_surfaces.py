from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "ci_changed_surfaces.py"
SECURITY_WORKFLOW = ROOT / ".github" / "workflows" / "security.yml"
TYPE_WORKFLOW = ROOT / ".github" / "workflows" / "type-check.yml"
NOTES_WORKFLOW = ROOT / ".github" / "workflows" / "project-notes-contract.yml"
DOCKER_WORKFLOW = ROOT / ".github" / "workflows" / "docker-build.yml"


def load_module():
    spec = importlib.util.spec_from_file_location("ci_changed_surfaces", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load ci_changed_surfaces")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODULE = load_module()
DOCKER_IMAGE_SURFACES = {
    "docker_velvet",
    "docker_supervisor",
    "docker_vision",
    "docker_krita",
    "docker_hermes",
}


class CiChangedSurfacesTests(unittest.TestCase):
    def test_docs_only_change_uses_preflight_without_targeted_or_full_tests(self) -> None:
        outputs = MODULE.classify_paths(
            ["docs/worklog/2026-08-04-ci-optimization.md", "README.md"]
        )
        self.assertTrue(outputs["tests_docs_only"])
        self.assertFalse(outputs["tests_targeted"])
        self.assertFalse(outputs["tests_full"])
        for name, enabled in outputs.items():
            if name != "tests_docs_only":
                self.assertFalse(enabled, name)

    def test_workflow_change_runs_ci_contracts_without_full_or_image_build(self) -> None:
        outputs = MODULE.classify_paths([".github/workflows/security.yml"])
        self.assertTrue(outputs["supply_chain"])
        self.assertTrue(outputs["codeql_actions"])
        self.assertFalse(outputs["codeql_python"])
        self.assertFalse(outputs["image"])
        self.assertTrue(outputs["tests_ci"])
        self.assertTrue(outputs["tests_targeted"])
        self.assertFalse(outputs["tests_full"])

    def test_selector_change_does_not_rebuild_production_image(self) -> None:
        outputs = MODULE.classify_paths(
            ["scripts/ci_changed_surfaces.py", "tests/test_ci_changed_surfaces.py"]
        )
        self.assertTrue(outputs["supply_chain"])
        self.assertTrue(outputs["codeql_python"])
        self.assertTrue(outputs["tests_ci"])
        self.assertTrue(outputs["tests_targeted"])
        self.assertFalse(outputs["image"])
        self.assertFalse(outputs["tests_full"])

    def test_python_change_selects_python_scanners_and_full_tests(self) -> None:
        outputs = MODULE.classify_paths(["velvet_bot/topics.py"])
        self.assertTrue(outputs["static_tools"])
        self.assertTrue(outputs["codeql_python"])
        self.assertTrue(outputs["image"])
        self.assertTrue(outputs["mypy"])
        self.assertTrue(outputs["tests_full"])

    def test_unbounded_python_change_does_not_run_mypy(self) -> None:
        outputs = MODULE.classify_paths(["scripts/check_project_notes.py"])
        self.assertTrue(outputs["static_tools"])
        self.assertTrue(outputs["codeql_python"])
        self.assertFalse(outputs["mypy"])
        self.assertTrue(outputs["tests_ci"])
        self.assertTrue(outputs["tests_targeted"])
        self.assertFalse(outputs["tests_full"])

    def test_dependency_change_runs_all_dependency_checks_and_full_tests(self) -> None:
        outputs = MODULE.classify_paths(["requirements.lock"])
        self.assertTrue(outputs["supply_chain"])
        self.assertTrue(outputs["dependency_audit"])
        self.assertTrue(outputs["image"])
        self.assertTrue(outputs["docker_velvet"])
        self.assertTrue(outputs["docker_any"])
        self.assertTrue(outputs["tests_full"])

    def test_hermes_change_builds_only_hermes_images_and_runs_targeted_tests(self) -> None:
        outputs = MODULE.classify_paths(
            ["deploy/hermes-operator/plugins/kael-coder-control/__init__.py"]
        )
        self.assertTrue(outputs["docker_hermes"])
        self.assertTrue(outputs["docker_any"])
        self.assertFalse(outputs["docker_krita"])
        self.assertFalse(outputs["docker_vision"])
        self.assertFalse(outputs["docker_velvet"])
        self.assertFalse(outputs["docker_supervisor"])
        self.assertTrue(outputs["tests_hermes"])
        self.assertTrue(outputs["tests_targeted"])
        self.assertFalse(outputs["tests_full"])

    def test_issue_593_change_set_builds_only_hermes_images(self) -> None:
        paths = [
            ".github/workflows/docker-build.yml",
            "deploy/hermes-coders/ensure_runtime_config.py",
            "deploy/hermes-entities/reconcile.sh",
            "deploy/hermes-operator/AGENTS.kael.md",
            "deploy/hermes-operator/install.sh",
            "deploy/hermes-operator/plugins/kael-coder-control/__init__.py",
            "deploy/hermes-operator/plugins/kael-coder-control/plugin.yaml",
            "docs/worklog/2026-08-04-issue-593-kael-fail-closed-coder-delegation.md",
            "scripts/ci_changed_surfaces.py",
            "tests/test_ci_changed_surfaces.py",
            "tests/test_docker_build_workflow_contract.py",
            "tests/test_hermes_kael_coder_control.py",
            "tests/test_hermes_kael_coder_control_deployment.py",
            "tests/test_hermes_runtime_config.py",
            "tests/test_hermes_tier_documentation_contract.py",
        ]
        outputs = MODULE.classify_paths(paths)
        self.assertTrue(outputs["docker_hermes"])
        self.assertTrue(outputs["docker_ci"])
        self.assertTrue(outputs["docker_any"])
        self.assertTrue(outputs["tests_ci"])
        self.assertTrue(outputs["tests_hermes"])
        self.assertTrue(outputs["tests_targeted"])
        self.assertFalse(outputs["tests_full"])
        for name in DOCKER_IMAGE_SURFACES - {"docker_hermes"}:
            self.assertFalse(outputs[name], name)

    def test_krita_change_builds_only_krita_image_and_runs_targeted_tests(self) -> None:
        outputs = MODULE.classify_paths(
            ["tools/krita/velvet_logo/velvet_logo.py"]
        )
        self.assertTrue(outputs["docker_krita"])
        self.assertTrue(outputs["docker_any"])
        self.assertTrue(outputs["tests_krita"])
        self.assertTrue(outputs["tests_targeted"])
        self.assertFalse(outputs["tests_full"])
        for name in DOCKER_IMAGE_SURFACES - {"docker_krita"}:
            self.assertFalse(outputs[name], name)

    def test_shared_docker_input_builds_every_image_and_runs_full_tests(self) -> None:
        outputs = MODULE.classify_paths([".dockerignore"])
        self.assertTrue(outputs["docker_any"])
        self.assertTrue(outputs["tests_full"])
        for name in DOCKER_IMAGE_SURFACES:
            self.assertTrue(outputs[name], name)

    def test_docker_workflow_change_selects_ci_contract_not_images(self) -> None:
        outputs = MODULE.classify_paths([".github/workflows/docker-build.yml"])
        self.assertTrue(outputs["docker_ci"])
        self.assertFalse(outputs["docker_any"])
        self.assertTrue(outputs["tests_ci"])
        self.assertTrue(outputs["tests_targeted"])
        self.assertFalse(outputs["tests_full"])
        for name in DOCKER_IMAGE_SURFACES:
            self.assertFalse(outputs[name], name)

    def test_unknown_new_surface_fails_closed_to_full_tests(self) -> None:
        outputs = MODULE.classify_paths(["new_subsystem/config.toml"])
        self.assertTrue(outputs["tests_full"])
        self.assertFalse(outputs["tests_targeted"])

    def test_empty_change_set_fails_closed_to_full_tests(self) -> None:
        outputs = MODULE.classify_paths([])
        self.assertTrue(outputs["tests_full"])

    def test_mixed_fast_and_application_paths_run_full_tests(self) -> None:
        outputs = MODULE.classify_paths(
            [
                "docs/worklog/example.md",
                "deploy/hermes-operator/install.sh",
                "velvet_bot/topics.py",
            ]
        )
        self.assertTrue(outputs["tests_targeted"])
        self.assertTrue(outputs["tests_full"])

    def test_pull_request_base_ref_fallback_avoids_full_scan(self) -> None:
        with patch.object(MODULE.subprocess, "run") as run, patch.object(
            MODULE,
            "_git",
            return_value="a" * 40,
        ):
            resolved = MODULE._resolve_pull_request_base(
                base_sha="",
                base_ref="main",
            )

        self.assertEqual("a" * 40, resolved)
        command = run.call_args.args[0]
        self.assertEqual("git", command[0])
        self.assertIn("main:refs/remotes/origin/main", command)

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
        self.assertIn("BASE_REF: ${{ github.base_ref }}", source)
        self.assertIn('--base-ref "$BASE_REF"', source)

    def test_project_notes_fetches_exact_base_without_obsolete_setup(self) -> None:
        source = NOTES_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("cancel-in-progress: true", source)
        self.assertIn("fetch-depth: 0", source)
        self.assertNotIn("fetch-depth: 2", source)
        self.assertNotIn("actions/setup-python", source)
        self.assertNotIn("git fetch", source)
        self.assertIn("github.event.pull_request.base.sha", source)

    def test_docker_workflow_builds_only_changed_surfaces_with_cache(self) -> None:
        source = DOCKER_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Resolve changed Docker surfaces", source)
        self.assertIn("--base-ref \"$BASE_REF\"", source)
        self.assertIn("github.event.pull_request.head.sha || github.sha", source)
        self.assertIn("steps.changes.outputs.docker_velvet == 'true'", source)
        self.assertIn("steps.changes.outputs.docker_supervisor == 'true'", source)
        self.assertIn("steps.changes.outputs.docker_vision == 'true'", source)
        self.assertIn("steps.changes.outputs.docker_krita == 'true'", source)
        self.assertIn("steps.changes.outputs.docker_hermes == 'true'", source)
        self.assertIn("--cache-from type=gha,scope=velvet-krita", source)
        self.assertIn("--cache-to type=gha,mode=max,scope=velvet-krita", source)
        self.assertIn("Skip unchanged Krita image", source)
        self.assertIn("Skip unchanged Hermes images", source)


if __name__ == "__main__":
    unittest.main()
