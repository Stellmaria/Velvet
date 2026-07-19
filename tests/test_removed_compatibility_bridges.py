from __future__ import annotations

import unittest
from pathlib import Path


class CompatibilityBridgePlacementTests(unittest.TestCase):
    def test_unused_discussion_dashboard_bridge_is_removed(self) -> None:
        package_source = Path("velvet_bot/handlers/__init__.py").read_text(
            encoding="utf-8"
        )
        router_source = Path("velvet_bot/presentation/telegram/router.py").read_text(
            encoding="utf-8"
        )

        self.assertNotIn("_get_discussion_dashboard", package_source)
        self.assertNotIn("get_discussion_dashboard_compat", package_source)
        self.assertNotIn("install_legacy_compatibility", package_source)
        self.assertNotIn("_get_discussion_dashboard", router_source)
        self.assertFalse(Path("velvet_bot/discussion_dashboard_compat.py").exists())


if __name__ == "__main__":
    unittest.main()
