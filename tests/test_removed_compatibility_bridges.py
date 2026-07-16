from __future__ import annotations

import unittest
from pathlib import Path


class RemovedCompatibilityBridgeTests(unittest.TestCase):
    def test_discussion_dashboard_monkeypatch_is_not_reintroduced(self) -> None:
        for path in (
            Path("velvet_bot/handlers/__init__.py"),
            Path("velvet_bot/presentation/telegram/router.py"),
        ):
            self.assertNotIn(
                "_get_discussion_dashboard",
                path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
