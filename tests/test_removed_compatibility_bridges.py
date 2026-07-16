from __future__ import annotations

import unittest
from pathlib import Path


class CompatibilityBridgePlacementTests(unittest.TestCase):
    def test_discussion_dashboard_bridge_exists_only_in_handlers_package(self) -> None:
        package_source = Path("velvet_bot/handlers/__init__.py").read_text(
            encoding="utf-8"
        )
        router_source = Path("velvet_bot/presentation/telegram/router.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("_get_discussion_dashboard", package_source)
        self.assertNotIn("_get_discussion_dashboard", router_source)


if __name__ == "__main__":
    unittest.main()
