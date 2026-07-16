from __future__ import annotations

import unittest
from pathlib import Path


class DiscussionArchitectureTests(unittest.TestCase):
    def test_legacy_insights_module_is_only_a_facade(self) -> None:
        source = Path("velvet_bot/discussion_insights.py").read_text(
            encoding="utf-8"
        )
        self.assertLessEqual(len(source.splitlines()), 70)
        self.assertNotIn("_require_pool", source)
        self.assertNotIn("SELECT ", source)
        self.assertNotIn("UPDATE ", source)

    def test_compatibility_layer_no_longer_patches_discussions(self) -> None:
        source = Path(
            "velvet_bot/presentation/telegram/compat.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("discussion_insights_module", source)
        self.assertNotIn("discussion_summary_runtime", source)


if __name__ == "__main__":
    unittest.main()
