from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
import tempfile
import threading
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch


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
delegate = load("issue584_delegate", "deploy/hermes-coders/codex_delegate.py")
sys.modules["coder_router"] = router
tier_router = load("issue584_tier_router", "deploy/hermes-operator/tier_router.py")
coderctl = load("issue584_coderctl", "deploy/hermes-operator/coderctl.py")


def ledger(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "task_id": "a" * 32,
        "run_id": "run-584",
        "workspace_path": "/opt/codex-runs/velvet/workspaces/run-584",
        "process_cwd": "/opt/codex-runs/velvet/workspaces/run-584",
        "base_workspace": "/workspace-base",
        "workspace_source_ref": "origin/main",
        "baseline_head": "1" * 40,
        "final_head": "2" * 40,
        "final_branch": "issue/584",
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
        "integration_results": (
            review.TrustedCheck("hermes-integration", "completed", "success"),
        ),
        "required_integration_checks": ("hermes-integration",),
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
                required_integration_checks=(),
            )
        )
        self.assertEqual(review.ReviewStatus.CHANGES_REQUESTED, decision.status)
        self.assertTrue(any("integration" in item for item in decision.review_findings))
        self.assertTrue(any("trusted integration" in item for item in decision.review_findings))

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

    def test_execution_event_alone_keeps_mutation_started_true(self) -> None:
        evidence = ledger(
            final_head="1" * 40,
            head_changed=False,
            branch_changed=False,
            refs_changed=False,
            working_tree_changed=False,
            execution_started=True,
            push_or_pr_observed=False,
            mutation_started=True,
        )
        self.assertTrue(review.mutation_from_ledger(evidence))
        self.assertEqual((), review.audit_ledger(evidence)[1])

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

    def test_missing_untyped_or_internally_inconsistent_audit_is_blocked(self) -> None:
        for invalid in (
            {
                key: value
                for key, value in ledger(mutation_started=False).items()
                if key not in {"head_changed", "refs_changed"}
            },
            ledger(mutation_started="false"),
            ledger(head_changed=False),
        ):
            with self.subTest(invalid=invalid):
                decision = review.evaluate_review(request(ledger=invalid))
                self.assertEqual(review.ReviewStatus.BLOCKED, decision.status)
                self.assertTrue(decision.evidence_conflict)

    def test_agent_style_integration_claim_is_not_trusted(self) -> None:
        decision = review.evaluate_review(
            request(
                integration_results=(
                    review.TrustedCheck(
                        "hermes-integration", "completed", "success", source="agent-report"
                    ),
                ),
            )
        )
        self.assertEqual(review.ReviewStatus.CHANGES_REQUESTED, decision.status)

    def test_skipped_or_neutral_check_cannot_prove_integration(self) -> None:
        for conclusion in ("skipped", "neutral"):
            with self.subTest(conclusion=conclusion):
                decision = review.evaluate_review(
                    request(
                        integration_results=(
                            review.TrustedCheck(
                                "hermes-integration", "completed", conclusion
                            ),
                        )
                    )
                )
                self.assertEqual(review.ReviewStatus.CHANGES_REQUESTED, decision.status)

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
    def test_complex_or_high_risk_always_uses_enhanced_review(self) -> None:
        for record in (
            {"requested_tier": "complex"},
            {"complexity": "complex"},
            {"risk": "high"},
            {"risk": "critical"},
        ):
            self.assertTrue(coderctl.requires_enhanced_review(record))
        self.assertFalse(
            coderctl.requires_enhanced_review(
                {"requested_tier": "standard", "complexity": "standard", "risk": "low"}
            )
        )

    def test_pr_evidence_must_match_task_head_branch_base_and_repository(self) -> None:
        record = {
            **ledger(),
            "repository": "Stellmaria/Velvet",
        }
        matching = {
            "head_sha": "2" * 40,
            "head_ref": "issue/584",
            "base_ref": "main",
            "repository": "Stellmaria/Velvet",
        }
        self.assertEqual((), coderctl.pr_evidence_findings(record, matching))
        for field in matching:
            mismatched = {**matching, field: "wrong"}
            self.assertTrue(coderctl.pr_evidence_findings(record, mismatched))

    def test_review_fix_counter_is_monotonic_and_bounded(self) -> None:
        self.assertEqual(0, coderctl.next_review_fix_iteration({}))
        self.assertEqual(
            1,
            coderctl.next_review_fix_iteration(
                {"review_status": "changes_requested", "review_fix_iterations": 0}
            ),
        )
        self.assertEqual(
            2,
            coderctl.next_review_fix_iteration(
                {"review_status": "changes_requested", "review_fix_iterations": 2}
            ),
        )
        with self.assertRaises(coderctl.CoderApiError):
            coderctl.next_review_fix_iteration({"review_fix_iterations": "0"})

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

    def test_direct_and_delegated_clients_share_http_router_identity_and_workspace_contract(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HERMES_CODER_ROUTER_CLIENT_TOKEN": "c" * 48,
                "HERMES_CODER_VELVET_TOKEN": "v" * 48,
                "HERMES_CODER_VELVET_GITHUB_TOKEN": "g" * 48,
            },
        ):
            service = tier_router.TierAwareCoderRouter()
        server = router.ThreadingHTTPServer(("127.0.0.1", 0), router.Handler)
        server.router = service
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        routing = {
            "task_type": "code",
            "complexity": "complex",
            "risk": "high",
            "mutation_policy": "isolated_pr_only",
            "requested_tier": "high_risk",
        }
        try:
            thread.start()
            with patch.object(
                service,
                "upstream",
                side_effect=(
                    {"run_id": "direct-run", "status": "queued"},
                    {"run_id": "delegated-run", "status": "queued"},
                ),
            ) as upstream, patch.dict(
                os.environ,
                {
                    "HERMES_CODEX_DELEGATE_URL": f"http://127.0.0.1:{server.server_port}",
                    "HERMES_CODER_ROUTER_CLIENT_TOKEN": "c" * 48,
                    "HERMES_CODEX_DELEGATE_PROJECT": "velvet",
                },
            ):
                direct_client = delegate.RunnerClient()
                direct_client.request(
                    "POST",
                    "/v1/coders/velvet/runs",
                    delegate.build_payload(
                        "direct", project="velvet", model=None, **routing
                    ),
                )
                delegated_client = coderctl.RouterClient()
                delegated_client.base_url = f"http://127.0.0.1:{server.server_port}"
                with patch.object(delegated_client, "_token", return_value="c" * 48):
                    delegated_client.submit(
                        "velvet",
                        task_id="d" * 32,
                        task="delegated",
                        source="kael-delegated",
                        **routing,
                    )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)
        self.assertEqual(2, upstream.call_count)
        prompts = [call.args[3]["input"] for call in upstream.call_args_list]
        self.assertIn('"source": "owner-direct"', prompts[0])
        self.assertIn('"source": "kael-delegated"', prompts[1])
        for prompt in prompts:
            self.assertIn('"identity": "Велвет"', prompt)
            self.assertIn("effective per-run path", prompt)
            self.assertNotIn("workspace=/workspace", prompt)

    def test_direct_client_is_fail_closed_when_router_is_unavailable(self) -> None:
        with patch.dict(
            os.environ,
            {
                "HERMES_CODEX_DELEGATE_URL": "http://127.0.0.1:1",
                "HERMES_CODER_ROUTER_CLIENT_TOKEN": "c" * 48,
                "HERMES_CODEX_DELEGATE_PROJECT": "velvet",
            },
        ), patch("urllib.request.urlopen", side_effect=urllib.error.URLError("down")):
            with self.assertRaises(delegate.DelegateError):
                delegate.RunnerClient().request("GET", "/v1/coders/velvet/capabilities")

    def test_coderctl_review_command_executes_gate_with_ledger_and_github_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "tasks.json"
            store = coderctl.Ledger(ledger_path)
            store.upsert(
                {
                    "task_id": "e" * 32,
                    "run_id": "run-584",
                    "project": "velvet",
                    "repository": "Stellmaria/Velvet",
                    "requested_tier": "high_risk",
                    "complexity": "complex",
                    "risk": "high",
                    "created_at": "2026-08-04T00:00:00+00:00",
                }
            )
            status_payload = {
                "status": "completed",
                "structured_output": {
                    "status": "completed",
                    "blocker": "",
                    "memory_candidates": [],
                },
                **ledger(),
            }
            pull_payload = {
                "repository": "Stellmaria/Velvet",
                "head_sha": "2" * 40,
                "head_ref": "issue/584",
                "base_ref": "main",
                "checks_success": True,
                "checks": [
                    {
                        "name": "hermes-integration",
                        "status": "completed",
                        "conclusion": "success",
                    }
                ],
                "files": ["client.py", "server.py"],
            }
            with patch.object(
                coderctl.RouterClient, "status", return_value=status_payload
            ), patch.object(
                coderctl.RouterClient, "pull_request", return_value=pull_payload
            ):
                exit_code = coderctl.main(
                    [
                        "--ledger",
                        str(ledger_path),
                        "review",
                        "e" * 32,
                        "--pr",
                        "584",
                        "--required-file",
                        "client.py",
                        "--required-file",
                        "server.py",
                        "--protocol-changed",
                        "--integration-check",
                        "hermes-integration",
                        "--rollout-only",
                        "host smoke",
                    ]
                )
            self.assertEqual(0, exit_code)
            saved = store.find("e" * 32)
            assert saved is not None
            self.assertEqual("review_approved", saved["stage"])

    def test_blocked_structured_output_is_never_promoted_to_implemented(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store = coderctl.Ledger(Path(directory) / "tasks.json")
            original = {
                "task_id": "f" * 32,
                "run_id": "blocked-run",
                "project": "velvet",
            }
            store.upsert(original)
            coderctl._update_from_status(
                store,
                original,
                {
                    "status": "completed",
                    "structured_output": {
                        "status": "blocked",
                        "blocker": "cannot implement",
                    },
                },
            )
            saved = store.find("f" * 32)
            assert saved is not None
            self.assertEqual("review_changes_requested", saved["readiness_stage"])

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
