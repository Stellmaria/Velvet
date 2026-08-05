from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy/hermes-coders"
OPERATOR = ROOT / "deploy/hermes-operator"
for path in (str(CODERS), str(OPERATOR)):
    if path not in sys.path:
        sys.path.insert(0, path)

context_runner = importlib.import_module("codex_context_launcher_runner")
coder_router = importlib.import_module("coder_router")
tier_router = importlib.import_module("tier_router")
evidence_router = importlib.import_module("evidence_router")


class _Response:
    def __init__(self, payload: object) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> bool:
        return False

    def read(self) -> bytes:
        return self._raw


class Issue584RuntimeEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.target = coder_router.CoderTarget(
            project="velvet",
            identity="Велвет",
            repository="Stellmaria/Velvet",
            bot_handle="@velvet_private_coder_bot",
            base_url="http://coder:8642",
            api_token="a" * 32,
            github_token="g" * 32,
        )

    def test_execution_evidence_ignores_lifecycle_only_output(self) -> None:
        lifecycle = json.dumps({"type": "thread.started"})
        execution = json.dumps({"item": {"type": "command_execution"}})
        self.assertFalse(
            context_runner.execution_started_from_evidence({}, lifecycle)
        )
        self.assertTrue(
            context_runner.execution_started_from_evidence({}, execution)
        )
        self.assertTrue(
            context_runner.execution_started_from_evidence(
                {"execution_started": True}
            )
        )

    def test_context_layer_does_not_redefine_mutation(self) -> None:
        source = (
            ROOT / "deploy/hermes-coders/codex_context_launcher_runner.py"
        ).read_text()
        tier_source = (ROOT / "deploy/hermes-coders/codex_tier_runner.py").read_text()
        success_body = source.split("def _success(", 1)[1].split("\ndef build_manager", 1)[0]
        self.assertNotIn("mutation_started=", success_body)
        self.assertIn(
            "mutation_started = git_mutated or push_or_pr_observed",
            tier_source,
        )
        for field in (
            "process_cwd",
            "final_branch",
            "execution_started",
            "push_or_pr_observed",
        ):
            self.assertIn(field, source)

    def test_canonical_compose_uses_context_launcher_for_both_projects(self) -> None:
        compose = (ROOT / "deploy/hermes-coders/compose.runtime.yaml").read_text()
        self.assertEqual(2, compose.count("/app/codex_context_launcher_runner.py"))
        self.assertEqual(
            2,
            compose.count(
                "./codex_context_launcher_runner.py:/app/codex_context_launcher_runner.py:ro"
            ),
        )
        guard = (ROOT / "deploy/hermes-coders/runtime_source_guard.py").read_text()
        self.assertIn('"codex_context_launcher_runner.py"', guard)
        self.assertIn("ContextLauncherTierProviderManager", guard)

    def test_runtime_router_keeps_typed_contract_and_effective_cwd(self) -> None:
        self.assertTrue(
            issubclass(
                evidence_router.EvidenceTierAwareCoderRouter,
                tier_router.TierAwareCoderRouter,
            )
        )
        handoff = tier_router.build_tier_handoff(
            self.target,
            task_id="a" * 32,
            task="Inspect the repository",
            source="owner-direct",
            routing={
                "task_type": "read_only",
                "complexity": "small",
                "risk": "low",
                "mutation_policy": "read_only",
                "requested_tier": "small",
            },
        )
        serialized = json.dumps(handoff, ensure_ascii=False)
        self.assertNotIn("workspace=/workspace", serialized)
        self.assertIn("current runner cwd", serialized)
        orchestration = (
            ROOT / "deploy/hermes-orchestration/compose.yaml"
        ).read_text()
        self.assertIn('/app/evidence_router.py', orchestration)

    def test_github_file_evidence_is_paginated(self) -> None:
        router = object.__new__(evidence_router.EvidenceTierAwareCoderRouter)
        router.timeout_seconds = 30
        first = [{"filename": f"file-{index:03d}.py"} for index in range(100)]
        second = [{"filename": "file-100.py"}]
        with patch.object(
            evidence_router.urllib.request,
            "urlopen",
            side_effect=[_Response(first), _Response(second)],
        ) as urlopen:
            result = router.github_list(self.target, "/pulls/640/files")
        self.assertEqual(101, len(result))
        self.assertIn("page=1", urlopen.call_args_list[0].args[0].full_url)
        self.assertIn("page=2", urlopen.call_args_list[1].args[0].full_url)

    def test_pr_snapshot_includes_sorted_files_and_fails_on_count_drift(self) -> None:
        router = object.__new__(evidence_router.EvidenceTierAwareCoderRouter)
        router.targets = {"velvet": self.target}
        router.timeout_seconds = 30
        base = {"changed_files": 2, "head_sha": "1" * 40}
        with patch.object(
            tier_router.TierAwareCoderRouter,
            "pull_request",
            return_value=base,
        ), patch.object(
            router,
            "github_list",
            return_value=[{"filename": "z.py"}, {"filename": "a.py"}],
        ):
            result = router.pull_request("velvet", 640)
        self.assertEqual(["a.py", "z.py"], result["files"])

        with patch.object(
            tier_router.TierAwareCoderRouter,
            "pull_request",
            return_value=base,
        ), patch.object(
            router,
            "github_list",
            return_value=[{"filename": "only.py"}],
        ):
            with self.assertRaises(coder_router.RouterError):
                router.pull_request("velvet", 640)

    def test_pr_snapshot_fails_closed_without_numeric_changed_files(self) -> None:
        router = object.__new__(evidence_router.EvidenceTierAwareCoderRouter)
        router.targets = {"velvet": self.target}
        router.timeout_seconds = 30
        with patch.object(
            tier_router.TierAwareCoderRouter,
            "pull_request",
            return_value={"head_sha": "1" * 40},
        ), patch.object(
            router,
            "github_list",
            return_value=[],
        ):
            with self.assertRaises(coder_router.RouterError):
                router.pull_request("velvet", 640)


if __name__ == "__main__":
    unittest.main()
