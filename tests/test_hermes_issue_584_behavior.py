from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


review = load("issue584_review_gate", "deploy/hermes-operator/review_gate.py")


def ledger(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_id": "a" * 32,
        "run_id": "run-584",
        "workspace_path": "/opt/codex-runs/velvet/workspaces/run-584",
        "workspace_source_ref": "origin/main",
        "baseline_head": "1" * 40,
        "final_head": "1" * 40,
        "head_changed": False,
        "branch_changed": False,
        "refs_changed": False,
        "working_tree_changed": False,
        "base_workspace_changed": False,
        "execution_started": True,
        "push_or_pr_observed": False,
        "mutation_started": False,
    }
    value.update(overrides)
    return value


def request(**overrides: object):
    value: dict[str, object] = {
        "coder_stage": "implemented_by_coder",
        "ci_green": True,
        "high_risk": False,
        "changed_files": frozenset(),
        "required_files": frozenset(),
        "ledger": ledger(),
        "process_cwd": "/opt/codex-runs/velvet/workspaces/run-584",
        "base_workspace": "/workspace-base",
    }
    value.update(overrides)
    return review.ReviewRequest(**value)


class Issue584ReadinessTests(unittest.TestCase):
    def test_green_ci_only_advances_to_review_pending(self) -> None:
        self.assertEqual(
            review.ReadinessStage.REVIEW_PENDING,
            review.readiness_after_coder("implemented_by_coder", ci_green=True),
        )

    def test_read_only_execution_does_not_inflate_mutation(self) -> None:
        evidence = ledger(execution_started=True, mutation_started=False)
        self.assertFalse(review.mutation_from_ledger(evidence))
        self.assertEqual((), review.audit_ledger(evidence)[1])
        decision = review.evaluate_review(request(ledger=evidence))
        self.assertEqual(review.ReviewStatus.APPROVED, decision.status)
        self.assertIn(
            "read-only execution started without mutation evidence",
            decision.verified_facts,
        )

    def test_real_git_or_push_evidence_requires_mutation_started(self) -> None:
        for changes in (
            {"final_head": "2" * 40, "head_changed": True},
            {"working_tree_changed": True},
            {"push_or_pr_observed": True},
        ):
            with self.subTest(changes=changes):
                evidence = ledger(**changes, mutation_started=True)
                self.assertTrue(review.mutation_from_ledger(evidence))
                self.assertEqual((), review.audit_ledger(evidence)[1])

    def test_inconsistent_mutation_evidence_blocks_review(self) -> None:
        evidence = ledger(working_tree_changed=True, mutation_started=False)
        decision = review.evaluate_review(request(ledger=evidence))
        self.assertEqual(review.ReviewStatus.BLOCKED, decision.status)
        self.assertTrue(decision.evidence_conflict)

    def test_github_mutation_conflict_blocks_review(self) -> None:
        decision = review.evaluate_review(
            request(ledger=ledger(), github_mutation_observed=True)
        )
        self.assertEqual(review.ReviewStatus.BLOCKED, decision.status)

    def test_workspace_must_match_process_and_not_resolve_to_base(self) -> None:
        mismatch = review.evaluate_review(request(process_cwd="/workspace"))
        self.assertEqual(review.ReviewStatus.CHANGES_REQUESTED, mismatch.status)
        shared = review.evaluate_review(
            request(
                ledger=ledger(workspace_path="/workspace-base/run-584"),
                process_cwd="/workspace-base/run-584",
            )
        )
        self.assertEqual(review.ReviewStatus.CHANGES_REQUESTED, shared.status)

    def test_manifest_distributes_engineering_evidence_policy(self) -> None:
        manifest = json.loads((ROOT / "brain-vault/manifest.json").read_text())
        serialized = json.dumps(manifest, ensure_ascii=False)
        self.assertGreaterEqual(
            serialized.count("brain-vault/policies/engineering-evidence.md"),
            3,
        )

    def test_policy_separates_execution_from_mutation(self) -> None:
        source = (ROOT / "brain-vault/policies/engineering-evidence.md").read_text()
        self.assertIn("execution_started=true", source)
        self.assertIn("mutation_started=false", source)
        self.assertIn("Сам по себе он не означает мутацию", source)


if __name__ == "__main__":
    unittest.main()
