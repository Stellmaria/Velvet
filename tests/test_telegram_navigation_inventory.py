from __future__ import annotations

import subprocess
import sys
import unittest


class TelegramNavigationInventoryTests(unittest.TestCase):
    def test_production_navigation_matches_mobile_contract(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/telegram_navigation_inventory.py",
                "--root",
                "velvet_bot",
                "--check",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        report = (result.stdout + "\n" + result.stderr).strip()
        self.assertEqual(0, result.returncode, report)


if __name__ == "__main__":
    unittest.main()
