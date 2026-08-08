from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "production-vl-benchmark.yml"
RUNBOOK = ROOT / "docs" / "LOCAL_VISION_RUNBOOK.md"


class ProductionVLBenchmarkWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = WORKFLOW.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")

    def test_workflow_is_manual_only_and_serialized_with_production(self) -> None:
        self.assertIn("workflow_dispatch:", self.text)
        self.assertNotIn("\n  push:", self.text)
        self.assertNotIn("\n  pull_request:", self.text)
        self.assertIn("group: velvet-production", self.text)
        self.assertIn("environment: production", self.text)
        self.assertIn("inputs.confirmation == 'BENCHMARK'", self.text)
        self.assertIn("github.ref == 'refs/heads/main'", self.text)

    def test_request_is_bounded_to_canonical_caps_and_small_sample_counts(self) -> None:
        for cap in ("384", "512", "768"):
            self.assertIn(f'- "{cap}"', self.text)
        for rounds in ("1", "3", "5"):
            self.assertIn(f'- "{rounds}"', self.text)
        self.assertIn('--timeout 360', self.text)
        self.assertIn('--max-output-tokens "$OUTPUT_CAP"', self.text)
        self.assertIn('--rounds "$ROUNDS"', self.text)
        self.assertIn("runtime/vision-benchmark", self.text)

    def test_workflow_fails_closed_on_production_vl_policy(self) -> None:
        required = (
            '"AI_QUALITY_ENABLED": "false"',
            '"AI_VISION_QUEUE_ENABLED": "false"',
            '"AI_VISION_CLOUD_PRO_ENABLED": "false"',
            '"AI_VISION_LOCAL_UNCENSORED_ENABLED": "false"',
            '"AI_VISION_MODEL": "qwen3.5:9b"',
            '"AI_VISION_FLASH_MODEL": "qwen3.5:9b"',
            '"VISION_MODEL": "qwen3.5:9b"',
            '"VISION_MODEL_EXPECTED_DIGEST": "6488c96fa5fa"',
            '"VISION_MAX_CONCURRENCY": "1"',
            '"VISION_REQUEST_TIMEOUT_SECONDS": "300"',
            '"STORAGE_LIBRARIAN_AUTO_ENQUEUE": "false"',
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.text)
        self.assertIn("--expected-digest 6488c96fa5fa", self.text)

    def test_workflow_requires_exact_verified_gateway_revision(self) -> None:
        self.assertIn(
            "ghcr\\.io/stellmaria/velvet-vision-gateway@sha256:[0-9a-f]{64}",
            self.text,
        )
        self.assertIn("gateway_revision=", self.text)
        self.assertIn("gateway_component=", self.text)
        self.assertIn('"${gateway_revision,,}" != "${SOURCE_COMMIT,,}"', self.text)
        self.assertIn('"$gateway_component" != "vision-gateway"', self.text)

    def test_workflow_fails_closed_on_container_state(self) -> None:
        required = (
            "assert_container_ready",
            "{{.State.Running}}",
            "{{.State.Paused}}",
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
            'current_bot_id="$("${compose[@]}" ps -q bot)"',
            'test "$current_bot_id" = "$bot_id"',
        )
        for fragment in required:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, self.text)

    def test_workflow_rejects_functionally_failed_scorecards(self) -> None:
        self.assertIn('payload.get("success_rate") != 1.0', self.text)
        self.assertIn('payload.get("failure_rate") != 0.0', self.text)
        self.assertIn('payload.get("schema_validity_rate") != 1.0', self.text)
        self.assertIn('sample.get("error") is not None', self.text)
        self.assertIn('sample.get("schema_valid") is not True', self.text)
        self.assertIn('BENCHMARK_EXIT_CODE', self.text)
        self.assertIn('if: always()', self.text)

    def test_workflow_does_not_mutate_runtime_or_enqueue_archive_work(self) -> None:
        forbidden = (
            "docker compose up",
            "docker compose pull",
            "docker compose restart",
            "docker pause",
            "docker unpause",
            "docker stop",
            "docker kill",
            "AI_QUALITY_ENABLED=true",
            "AI_VISION_CLOUD_PRO_ENABLED=true",
            "AI_VISION_LOCAL_UNCENSORED_ENABLED=true",
            "quality_plan_start",
            "claim_targets",
        )
        for fragment in forbidden:
            with self.subTest(fragment=fragment):
                self.assertNotIn(fragment, self.text)

    def test_artifact_contains_scorecard_not_source_image(self) -> None:
        self.assertIn("path: benchmark.json", self.text)
        self.assertNotIn("path: ${{ inputs.image_name }}", self.text)
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", self.text)

    def test_runbook_uses_same_closed_set_directory_and_first_smoke_inputs(self) -> None:
        self.assertIn("runtime/vision-benchmark/smoke-neutral.jpg", self.runbook)
        self.assertNotIn("runtime/vision-benchmark.jpg", self.runbook)
        self.assertIn("confirmation=BENCHMARK", self.runbook)
        self.assertIn("output_cap=512", self.runbook)
        self.assertIn("rounds=1", self.runbook)
        self.assertIn("cold_unload=false", self.runbook)
        self.assertIn("production-vl-benchmark.yml", self.runbook)
        self.assertIn("не ставьте production-контейнеры на `docker pause`", self.runbook)


if __name__ == "__main__":
    unittest.main()
