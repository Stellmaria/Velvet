from __future__ import annotations

import importlib.util
import json
import stat
import sys
import tempfile
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
router = load("issue584_router", "deploy/hermes-operator/coder_router.py")


def ledger(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_id": "a" * 32,
        "run_id": "run-584",
        "workspace_path": "/opt/codex-runs/velvet/workspaces/run-584",
        "workspace_source_ref": "origin/main",
        "baseline_head": "1" * 40,
        "final_head": "2" * 40,
        "head_changed": True,
        "branch_changed": True,
        "refs_changed": True,
        "working_tree_changed": False,
        "base_workspace_changed": False,
        "execution_started": True,
        "push_or_pr_observed": True,
        "mutation_started": True,
        "actual_route": "codex_subscription:gpt-5.6-sol",
    }
    value.update(overrides)
    return value


def request(**overrides: object):
    value: dict[str, object] = {
        "coder_stage": "implemented_by_coder",
        "ci_green": True,
        "high_risk": True,
        "changed_files": frozenset({"client.py", "server.py", "integration_test.py"}),
        "required_files": frozenset({"client.py", "server.py"}),
        "protocol_changed": True,
        "integration_results": ("client -> public server handler -> mocked upstream: pass",),
        "test_evidence": (review.EvidenceLevel.INTEGRATION_PUBLIC_INTERFACE,),
        "ledger": ledger(),
        "process_cwd": "/opt/codex-runs/velvet/workspaces/run-584",
        "base_workspace": "/workspace-base",
        "rollout_only_checks": ("host identity smoke",),
    }
    value.update(overrides)
    return review.ReviewRequest(**value)


class ReadinessBehaviorTests(unittest.TestCase):
    def test_green_ci_without_review_stays_review_pending(self) -> None:
        self.assertEqual(
            review.ReadinessStage.REVIEW_PENDING,
            review.readiness_after_coder("implemented_by_coder", ci_green=True),
        )
        with self.assertRaises(ValueError):
            review.readiness_after_coder("running", ci_green=True)

    def test_coder_completion_and_green_ci_are_only_review_pending_inputs(self) -> None:
        decision = review.evaluate_review(request())
        self.assertEqual(review.ReviewStatus.APPROVED, decision.status)
        self.assertEqual(review.ReadinessStage.REVIEW_APPROVED, decision.stage)
        self.assertNotEqual(review.ReadinessStage.COMPLETED, decision.stage)
        self.assertIn("host identity smoke", decision.rollout_only_checks)
        self.assertIn("host identity smoke", decision.agent_claims_not_independently_verified)

    def test_review_findings_request_changes_not_completion(self) -> None:
        decision = review.evaluate_review(request(findings=("schema mismatch",)))
        self.assertEqual(review.ReviewStatus.CHANGES_REQUESTED, decision.status)
        self.assertEqual(review.ReadinessStage.REVIEW_CHANGES_REQUESTED, decision.stage)
        self.assertTrue(decision.delegate_fix)

    def test_requirement_coverage_detects_mandatory_unchanged_file(self) -> None:
        decision = review.evaluate_review(
            request(required_files=frozenset({"client.py", "server.py", "manifest.json"}))
        )
        self.assertTrue(
            any("manifest.json" in finding for finding in decision.review_findings)
        )

    def test_protocol_change_and_static_only_suite_fail_high_risk_review(self) -> None:
        decision = review.evaluate_review(
            request(
                integration_results=(),
                test_evidence=(review.EvidenceLevel.STATIC_CONTRACT,),
            )
        )
        self.assertEqual(review.ReviewStatus.CHANGES_REQUESTED, decision.status)
        self.assertTrue(any("integration" in item for item in decision.review_findings))
        self.assertTrue(any("static/unit" in item for item in decision.review_findings))

    def test_evidence_hierarchy_never_promotes_a_weaker_level(self) -> None:
        self.assertFalse(
            review.evidence_satisfies(
                (review.EvidenceLevel.SOURCE_MARKER,),
                review.EvidenceLevel.INTEGRATION_PUBLIC_INTERFACE,
            )
        )
        self.assertTrue(
            review.evidence_satisfies(
                (review.EvidenceLevel.REAL_CONTAINER_EXECUTION,),
                review.EvidenceLevel.INTEGRATION_PUBLIC_INTERFACE,
            )
        )

    def test_workspace_mismatch_and_shared_base_are_fail_closed(self) -> None:
        mismatch = review.evaluate_review(request(process_cwd="/workspace"))
        self.assertEqual(review.ReviewStatus.CHANGES_REQUESTED, mismatch.status)
        shared = review.evaluate_review(
            request(
                ledger=ledger(workspace_path="/workspace-base/run-584"),
                process_cwd="/workspace-base/run-584",
            )
        )
        self.assertEqual(review.ReviewStatus.CHANGES_REQUESTED, shared.status)
        self.assertTrue(any("shared/base" in item for item in shared.review_findings))

    def test_clean_after_commit_still_computes_mutation(self) -> None:
        evidence = ledger(working_tree_changed=False, mutation_started=True)
        self.assertTrue(review.mutation_from_ledger(evidence))
        decision = review.evaluate_review(request(ledger=evidence))
        self.assertIn(
            "mutation_started is supported by trusted evidence",
            decision.verified_facts,
        )

    def test_ledger_github_conflict_blocks_review_approval(self) -> None:
        evidence = ledger(
            head_changed=False,
            branch_changed=False,
            refs_changed=False,
            execution_started=False,
            push_or_pr_observed=False,
            mutation_started=False,
        )
        decision = review.evaluate_review(
            request(ledger=evidence, github_mutation_observed=True)
        )
        self.assertEqual(review.ReviewStatus.BLOCKED, decision.status)
        self.assertTrue(decision.evidence_conflict)
        self.assertFalse(decision.delegate_fix)

    def test_second_fix_iteration_escalates_and_preserves_existing_pr(self) -> None:
        decision = review.evaluate_review(
            request(findings=("new blocker",), review_fix_iterations=2)
        )
        self.assertEqual(review.ReviewStatus.CHANGES_REQUESTED, decision.status)
        self.assertFalse(decision.delegate_fix)
        self.assertIn("preserve the existing PR", decision.recommended_next_action)

    def test_agent_cannot_override_trusted_route_or_mutation_metadata(self) -> None:
        trusted = ledger(actual_route="trusted-route", mutation_started=True)
        metadata = review.trusted_route_metadata(
            trusted,
            {"actual_route": "invented-route", "mutation_started": False},
        )
        self.assertEqual("trusted-route", metadata["actual_route"])
        self.assertIs(True, metadata["mutation_started"])


class IdentityAndContextIntegrationTests(unittest.TestCase):
    def test_direct_and_delegated_handoffs_keep_one_identity_and_no_static_workspace(self) -> None:
        for project, expected in (("velvet", "Велвет"), ("max", "Макс")):
            target = router.load_targets()[project]
            direct = router.build_task_handoff(
                target, task_id="b" * 32, task="inspect", source="owner-direct"
            )
            delegated = router.build_task_handoff(
                target, task_id="c" * 32, task="inspect", source="kael-delegated"
            )
            self.assertEqual(expected, direct["identity"])
            self.assertEqual(expected, delegated["identity"])
            self.assertEqual(direct["identity"], delegated["identity"])
            self.assertNotIn("workspace=/workspace", json.dumps(direct))
            self.assertIn("effective per-run workspace", direct["context"])

    def test_compile_install_verify_preserves_hashes_and_private_permissions(self) -> None:
        brain = ROOT / "deploy/hermes-brain"
        sys.path.insert(0, str(brain))
        import context_compiler as compiler
        import install_context_pack as installer
        import verify_installed_context as verifier

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for entity, mode in (("kael", "hermes"), ("velvet-coder", "codex"), ("max-coder", "codex")):
                pack = root / f"pack-{entity}"
                target = root / f"target-{entity}"
                target.mkdir()
                compiler.compile_entity(ROOT, entity, pack)
                compiler.verify_pack(pack, expected_entity=entity)
                installer.install_pack(pack, target, entity=entity, mode=mode)
                verifier.verify_installed(target, entity=entity, mode=mode)
                manifest = target / "context-manifest.json"
                self.assertEqual(0o600, stat.S_IMODE(manifest.stat().st_mode))
                self.assertEqual(0, manifest.stat().st_mode & 0o077)


if __name__ == "__main__":
    unittest.main()
