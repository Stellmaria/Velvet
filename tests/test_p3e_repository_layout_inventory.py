from __future__ import annotations

import json
import unittest

from scripts.inventory_repository_layout import build_inventory


class P3ERepositoryLayoutInventoryTests(unittest.TestCase):
    def test_discovery_baseline_is_captured(self) -> None:
        inventory = build_inventory(label="p3e-repository-layout-baseline")
        self.fail(
            "P3E_REPOSITORY_LAYOUT_DISCOVERY="
            + json.dumps(inventory, ensure_ascii=False, separators=(",", ":"))
        )


if __name__ == "__main__":
    unittest.main()
