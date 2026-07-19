from __future__ import annotations

import inspect
import json
import unittest
from pathlib import Path

import velvet_bot.analytics_dashboard as analytics_dashboard
import velvet_bot.handlers.quality_set_ai as quality_set_ai
import velvet_bot.handlers.quality_sets as quality_sets
import velvet_bot.handlers.reference_comparison as reference_comparison
import velvet_bot.media_set_actions as media_set_actions
import velvet_bot.media_set_duplicate_actions as duplicate_actions
import velvet_bot.media_set_duplicate_actions_repository as duplicate_repository
import velvet_bot.quality_set_ai_repository as set_ai_repository
import velvet_bot.quality_sets_repository as sets_repository
import velvet_bot.reference_comparison_repository as comparison_repository

ROOT = Path(__file__).resolve().parents[1]


class Phase18CompletionTests(unittest.TestCase):
    def test_private_pool_baseline_is_empty(self) -> None:
        baseline = json.loads(
            (ROOT / "docs/private_pool_inventory.json").read_text(encoding="utf-8")
        )
        self.assertEqual(0, baseline["total_external_findings"])
        self.assertEqual(0, baseline["total_files"])
        self.assertEqual([], baseline["files"])

    def test_application_services_do_not_own_connections(self) -> None:
        for module in (media_set_actions, duplicate_actions):
            source = inspect.getsource(module)
            self.assertNotIn("_require_pool", source)
            self.assertNotIn("database.acquire()", source)

    def test_handlers_do_not_own_connections(self) -> None:
        for module in (quality_set_ai, quality_sets, reference_comparison):
            source = inspect.getsource(module)
            self.assertNotIn("_require_pool", source)
            self.assertNotIn("database.acquire()", source)

    def test_repository_boundaries_use_public_acquire(self) -> None:
        expected = {
            duplicate_repository: 1,
            set_ai_repository: 4,
            sets_repository: 2,
            comparison_repository: 1,
        }
        for module, count in expected.items():
            source = inspect.getsource(module)
            self.assertNotIn("_require_pool", source)
            self.assertEqual(count, source.count("database.acquire()"))

    def test_discussion_dashboard_uses_canonical_public_boundary(self) -> None:
        source = inspect.getsource(analytics_dashboard.get_discussion_dashboard)
        self.assertIn("database.acquire()", source)
        self.assertNotIn("_require_pool", source)
        self.assertFalse((ROOT / "velvet_bot/discussion_dashboard_compat.py").exists())


if __name__ == "__main__":
    unittest.main()
