from __future__ import annotations

import json
import unittest
from pathlib import Path

from scripts.inventory_repository_layout import build_inventory, render_markdown


ROOT = Path(__file__).resolve().parents[1]
LABEL = "p3e-repository-layout-baseline"
NOTIFICATION_REPOSITORY = (
    "velvet_bot.repositories." + "public_notification_repository"
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

    def test_package_exports_are_not_runtime_consumers(self) -> None:
        inventory = build_inventory(label=LABEL)
        modules = {item["module"]: item for item in inventory["modules"]}
        notification_repository = modules[NOTIFICATION_REPOSITORY]

        self.assertEqual(0, notification_repository["production_consumer_count"])
        self.assertEqual(0, notification_repository["test_consumer_count"])
        self.assertEqual(1, notification_repository["package_export_count"])
        self.assertIn(
            NOTIFICATION_REPOSITORY,
            inventory["export_only_repository_modules"],
        )

    def test_first_slice_is_measurable(self) -> None:
        inventory = build_inventory(label=LABEL)

        self.assertEqual(33, inventory["repository_module_count"])
        self.assertEqual(23, inventory["layout_counts"]["domain"])
        self.assertEqual(3, inventory["layout_counts"]["central"])
        self.assertEqual(7, inventory["layout_counts"]["root"])
        self.assertEqual(
            NOTIFICATION_REPOSITORY,
            inventory["next_slice"]["candidate"],
        )


if __name__ == "__main__":
    unittest.main()
