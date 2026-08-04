from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "type-check.yml"


class TypeCheckCheckoutWorkflowContractTests(unittest.TestCase):
    def test_surface_detection_uses_shallow_exact_commits(self) -> None:
        source = WORKFLOW.read_text(encoding="utf-8")

        self.assertIn("Checkout exact change head", source)
        self.assertIn("fetch-depth: 1", source)
        self.assertNotIn("fetch-depth: 0", source)
        self.assertIn("Fetch exact pull request base", source)
        self.assertIn('git fetch --no-tags --depth=1 origin "$BASE_SHA"', source)


if __name__ == "__main__":
    unittest.main()
