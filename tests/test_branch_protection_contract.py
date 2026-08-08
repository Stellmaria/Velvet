from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BranchProtectionContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source = (
            ROOT / ".github/workflows/branch-protection-contract.yml"
        ).read_text(encoding="utf-8")

    def test_docker_gate_uses_pull_request_head_sha(self) -> None:
        self.assertIn(
            "GH_SHA: ${{ github.event.pull_request.head.sha || github.sha }}",
            self.source,
        )
        self.assertIn(
            "group: branch-protection-${{ github.event.pull_request.number || github.ref }}",
            self.source,
        )
        self.assertIn("cancel-in-progress: true", self.source)
        self.assertNotIn("GH_SHA: ${{ github.sha }}", self.source)

    def test_docker_gate_polls_without_large_completion_tail(self) -> None:
        self.assertIn("poll_interval_seconds = 5", self.source)
        self.assertGreaterEqual(
            self.source.count("time.sleep(poll_interval_seconds)"),
            2,
        )
        self.assertNotIn("time.sleep(15)", self.source)


if __name__ == "__main__":
    unittest.main()
