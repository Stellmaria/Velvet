from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class BranchProtectionContractTests(unittest.TestCase):
    def test_docker_gate_uses_pull_request_head_sha(self) -> None:
        source = (
            ROOT / ".github/workflows/branch-protection-contract.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "GH_SHA: ${{ github.event.pull_request.head.sha || github.sha }}",
            source,
        )
        self.assertIn(
            "group: branch-protection-${{ github.event.pull_request.number || github.ref }}",
            source,
        )
        self.assertIn("cancel-in-progress: true", source)
        self.assertNotIn("GH_SHA: ${{ github.sha }}", source)


if __name__ == "__main__":
    unittest.main()
