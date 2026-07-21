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
NEXT_PUBLICATION_REPOSITORY = (
    "velvet_bot.repositories." + "publication_repository"
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

    def test_retired_notification_repository_is_absent(self) -> None:
        inventory = build_inventory(label=LABEL)
        modules = {item["module"] for item in inventory["modules"]}
        repository_package = (
            ROOT / "velvet_bot/repositories/__init__.py"
        ).read_text(encoding="utf-8")

        self.assertNotIn(RETIRED_NOTIFICATION_REPOSITORY, modules)
        self.assertNotIn("PublicNotificationRepository", repository_package)
        self.assertNotIn("PendingPublicNotification", repository_package)
        self.assertFalse(
            (ROOT / "velvet_bot/repositories/public_notification_repository.py").exists()
        )

    def test_next_slice_is_measurable(self) -> None:
        inventory = build_inventory(label=LABEL)

        self.assertEqual(32, inventory["repository_module_count"])
        self.assertEqual(23, inventory["layout_counts"]["domain"])
        self.assertEqual(2, inventory["layout_counts"]["central"])
        self.assertEqual(7, inventory["layout_counts"]["root"])
        self.assertEqual(
            NEXT_PUBLICATION_REPOSITORY,
            inventory["next_slice"]["candidate"],
        )


if __name__ == "__main__":
    unittest.main()
