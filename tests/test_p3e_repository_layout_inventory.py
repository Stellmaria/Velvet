from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.inventory_repository_layout import build_inventory, render_markdown


ROOT = Path(__file__).resolve().parents[1]
LABEL = "p3e-repository-layout-complete"
RETIRED_NOTIFICATION_REPOSITORY = (
    "velvet_bot.repositories." + "public_notification_repository"
)
RETIRED_PUBLICATION_REPOSITORY = (
    "velvet_bot.repositories." + "publication_repository"
)
RETIRED_ROOT_CANDIDATE_REPOSITORY = (
    "velvet_bot." + "media_set_candidate_listing_repository"
)
CANONICAL_MEDIA_SET_REPOSITORY = (
    "velvet_bot.domains.media_sets." + "repository"
)
RETIRED_ROOT_DUPLICATE_REPOSITORY = (
    "velvet_bot." + "media_set_duplicate_actions_repository"
)
CANONICAL_DUPLICATE_REPOSITORY = (
    "velvet_bot.domains.media_sets." + "duplicate_actions_repository"
)
RETIRED_ROOT_SET_AI_REPOSITORY = "velvet_bot." + "quality_set_ai_repository"
CANONICAL_SET_AI_REPOSITORY = (
    "velvet_bot.domains.media_sets." + "ai_repository"
)
RETIRED_ROOT_QUALITY_REPOSITORY = "velvet_bot." + "quality_sets_repository"
CANONICAL_QUALITY_REPOSITORY = (
    "velvet_bot.domains.media_sets." + "quality_repository"
)
RETIRED_ROOT_REFERENCE_REPOSITORY = (
    "velvet_bot." + "reference_comparison_repository"
)
CANONICAL_REFERENCE_REPOSITORY = (
    "velvet_bot.domains.references." + "comparison_repository"
)
RETIRED_ROOT_ACTIONS_REPOSITORY = (
    "velvet_bot." + "media_set_actions_repository"
)
CANONICAL_ACTIONS_REPOSITORY = (
    "velvet_bot.domains.media_sets." + "actions_repository"
)
RETIRED_ROOT_DISCOVERY_REPOSITORY = (
    "velvet_bot." + "media_set_ai_repository"
)
CANONICAL_DISCOVERY_REPOSITORY = (
    "velvet_bot.domains.media_sets." + "discovery_repository"
)
RETIRED_CENTRAL_SYSTEM_REPOSITORY = (
    "velvet_bot.repositories." + "system_repository"
)
CANONICAL_SYSTEM_REPOSITORY = (
    "velvet_bot.infrastructure.postgres." + "system_repository"
)


class P3ERepositoryLayoutInventoryTests(unittest.TestCase):
    def test_generated_inventory_matches_repository(self) -> None:
        inventory = build_inventory(label=LABEL)
        stored = json.loads(
            (ROOT / "docs/repository_layout_inventory.json").read_text(
                encoding="utf-8"
            )
        )
        markdown = (ROOT / "docs/repository_layout_inventory.md").read_text(
            encoding="utf-8"
        )

        self.assertEqual(inventory, stored)
        self.assertEqual(render_markdown(inventory), markdown)

    def test_retired_repository_paths_are_absent(self) -> None:
        inventory = build_inventory(label=LABEL)
        modules = {item["module"] for item in inventory["modules"]}

        self.assertNotIn(RETIRED_NOTIFICATION_REPOSITORY, modules)
        self.assertNotIn(RETIRED_PUBLICATION_REPOSITORY, modules)
        self.assertNotIn(RETIRED_ROOT_CANDIDATE_REPOSITORY, modules)
        self.assertNotIn(RETIRED_ROOT_DUPLICATE_REPOSITORY, modules)
        self.assertNotIn(RETIRED_ROOT_SET_AI_REPOSITORY, modules)
        self.assertNotIn(RETIRED_ROOT_QUALITY_REPOSITORY, modules)
        self.assertNotIn(RETIRED_ROOT_REFERENCE_REPOSITORY, modules)
        self.assertNotIn(RETIRED_ROOT_ACTIONS_REPOSITORY, modules)
        self.assertNotIn(RETIRED_ROOT_DISCOVERY_REPOSITORY, modules)
        self.assertNotIn(RETIRED_CENTRAL_SYSTEM_REPOSITORY, modules)
        self.assertIn(CANONICAL_MEDIA_SET_REPOSITORY, modules)
        self.assertIn(CANONICAL_DUPLICATE_REPOSITORY, modules)
        self.assertIn(CANONICAL_SET_AI_REPOSITORY, modules)
        self.assertIn(CANONICAL_QUALITY_REPOSITORY, modules)
        self.assertIn(CANONICAL_REFERENCE_REPOSITORY, modules)
        self.assertIn(CANONICAL_ACTIONS_REPOSITORY, modules)
        self.assertIn(CANONICAL_DISCOVERY_REPOSITORY, modules)
        self.assertIn(CANONICAL_SYSTEM_REPOSITORY, modules)
        self.assertFalse((ROOT / "velvet_bot/repositories/__init__.py").exists())
        self.assertFalse(
            (ROOT / "velvet_bot/repositories/system_repository.py").exists()
        )
        self.assertFalse(
            (ROOT / "velvet_bot/media_set_candidate_listing_repository.py").exists()
        )
        self.assertFalse(
            (ROOT / "velvet_bot/media_set_duplicate_actions_repository.py").exists()
        )
        self.assertFalse(
            (ROOT / "velvet_bot/quality_set_ai_repository.py").exists()
        )
        self.assertFalse(
            (ROOT / "velvet_bot/quality_sets_repository.py").exists()
        )
        self.assertFalse(
            (ROOT / "velvet_bot/reference_comparison_repository.py").exists()
        )
        self.assertFalse(
            (ROOT / "velvet_bot/media_set_actions_repository.py").exists()
        )
        self.assertFalse(
            (ROOT / "velvet_bot/media_set_ai_repository.py").exists()
        )
        self.assertTrue(
            (ROOT / "velvet_bot/domains/media_sets/repository.py").is_file()
        )
        self.assertTrue(
            (
                ROOT
                / "velvet_bot/domains/media_sets/duplicate_actions_repository.py"
            ).is_file()
        )
        self.assertTrue(
            (ROOT / "velvet_bot/domains/media_sets/ai_repository.py").is_file()
        )
        self.assertTrue(
            (ROOT / "velvet_bot/domains/media_sets/quality_repository.py").is_file()
        )
        self.assertTrue(
            (
                ROOT
                / "velvet_bot/domains/references/comparison_repository.py"
            ).is_file()
        )
        self.assertTrue(
            (ROOT / "velvet_bot/domains/media_sets/actions_repository.py").is_file()
        )
        self.assertTrue(
            (ROOT / "velvet_bot/domains/media_sets/discovery_repository.py").is_file()
        )
        self.assertTrue(
            (
                ROOT
                / "velvet_bot/infrastructure/postgres/system_repository.py"
            ).is_file()
        )

    def test_repository_layout_migration_is_complete(self) -> None:
        inventory = build_inventory(label=LABEL)

        self.assertEqual(31, inventory["repository_module_count"])
        self.assertEqual(30, inventory["layout_counts"]["domain"])
        self.assertEqual(1, inventory["layout_counts"]["infrastructure"])
        self.assertEqual(0, inventory["layout_counts"].get("central", 0))
        self.assertEqual(0, inventory["layout_counts"].get("root", 0))
        self.assertEqual(110, inventory["root_module_count"])
        self.assertIsNone(inventory["next_slice"]["candidate"])
        self.assertEqual(
            "repository layout migration complete",
            inventory["next_slice"]["target"],
        )


if __name__ == "__main__":
    unittest.main()
