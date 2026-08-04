from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "tests.yml"


class SelectiveTestsWorkflowContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = WORKFLOW.read_text(encoding="utf-8")

    def test_required_unit_test_context_is_always_aggregated(self) -> None:
        self.assertIn("name: unit-tests", self.source)
        self.assertIn("if: always()", self.source)
        self.assertIn("Verify selected test jobs", self.source)
        self.assertIn('test "$CHANGES_RESULT" = "success"', self.source)
        self.assertIn('test "$PREFLIGHT_RESULT" = "success"', self.source)

    def test_full_shards_run_only_for_full_surface(self) -> None:
        self.assertIn("name: test-shard-${{ matrix.shard }}", self.source)
        self.assertIn(
            "if: needs.changes.outputs.tests_full == 'true'",
            self.source,
        )
        self.assertIn("Start native PostgreSQL", self.source)
        self.assertIn("matrix:\n        shard: [0, 1, 2, 3]", self.source)

    def test_targeted_contracts_run_without_postgresql(self) -> None:
        self.assertIn("name: targeted-contracts", self.source)
        self.assertIn("needs.changes.outputs.tests_full != 'true'", self.source)
        self.assertIn("needs.changes.outputs.tests_targeted == 'true'", self.source)
        targeted = self.source.split("  targeted-contracts:", 1)[1].split(
            "  test-shards:", 1
        )[0]
        self.assertNotIn("Start native PostgreSQL", targeted)
        self.assertIn('patterns.append("test_hermes_*.py")', targeted)
        self.assertIn('patterns.append("test_krita_*.py")', targeted)
        self.assertIn('"test_*workflow_contract.py"', targeted)

    def test_selector_uses_current_base_ref_and_exact_pr_head(self) -> None:
        self.assertIn("name: resolve-test-surfaces", self.source)
        self.assertIn("BASE_REF: ${{ github.base_ref }}", self.source)
        self.assertIn('--base-ref "$BASE_REF"', self.source)
        self.assertGreaterEqual(
            self.source.count("github.event.pull_request.head.sha || github.sha"),
            3,
        )

    def test_nightly_full_suite_remains_available(self) -> None:
        self.assertIn('cron: "41 2 * * *"', self.source)
        self.assertIn("workflow_dispatch:", self.source)

    def test_aggregator_requires_success_or_expected_skip(self) -> None:
        self.assertIn('test "$SHARDS_RESULT" = "success"', self.source)
        self.assertIn('test "$SHARDS_RESULT" = "skipped"', self.source)
        self.assertIn('test "$TARGETED_RESULT" = "success"', self.source)
        self.assertIn('test "$TARGETED_RESULT" = "skipped"', self.source)


if __name__ == "__main__":
    unittest.main()
