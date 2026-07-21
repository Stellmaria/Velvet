from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.inventory_repository_layout import build_inventory, render_markdown


ROOT = Path(__file__).resolve().parents[1]
LABEL = "p3e-repository-layout-baseline"
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
NEXT_ROOT_REPOSITORY = "velvet_bot." + "quality_set_ai_repository"


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
        repository_package = (
            ROOT / "velvet_bot/repositories/__init__.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn(RETIRED_NOTIFICATION_REPOSITORY, modules)
        self.assertNotIn(RETIRED_PUBLICATION_REPOSITORY, modules)
        self.assertNotIn(RETIRED_ROOT_CANDIDATE_REPOSITORY, modules)
        self.assertNotIn(RETIRED_ROOT_DUPLICATE_REPOSITORY, modules)
        self.assertIn(CANONICAL_MEDIA_SET_REPOSITORY, modules)
        self.assertIn(CANONICAL_DUPLICATE_REPOSITORY, modules)
        self.assertNotIn("PublicNotificationRepository", repository_package)
        self.assertNotIn("PendingPublicNotification", repository_package)
        self.assertNotIn("PublicationRepository", repository_package)
        self.assertFalse(
            (ROOT / "velvet_bot/repositories/public_notification_repository.py").exists()
        )
        self.assertFalse(
            (ROOT / "velvet_bot/repositories/publication_repository.py").exists()
        )
        self.assertFalse(
            (ROOT / "velvet_bot/media_set_candidate_listing_repository.py").exists()
        )
        self.assertFalse(
            (ROOT / "velvet_bot/media_set_duplicate_actions_repository.py").exists()
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

    def test_next_slice_is_measurable(self) -> None:
        inventory = build_inventory(label=LABEL)

        self.assertEqual(31, inventory["repository_module_count"])
        self.assertEqual(25, inventory["layout_counts"]["domain"])
        self.assertEqual(1, inventory["layout_counts"]["central"])
        self.assertEqual(5, inventory["layout_counts"]["root"])
        self.assertEqual(115, inventory["root_module_count"])
        self.assertEqual(
            NEXT_ROOT_REPOSITORY,
            inventory["next_slice"]["candidate"],
        )


if __name__ == "__main__":
    unittest.main()
