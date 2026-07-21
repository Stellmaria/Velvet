from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class TelegramNavigationInventoryTests(unittest.TestCase):
    def _run_inventory(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                sys.executable,
                "scripts/telegram_navigation_inventory.py",
                "--root",
                "velvet_bot",
                *extra,
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    def test_production_navigation_matches_mobile_contract(self) -> None:
        result = self._run_inventory("--check")
        report = (result.stdout + "\n" + result.stderr).strip()
        self.assertEqual(0, result.returncode, report)

    def test_generated_inventory_is_current(self) -> None:
        expected = Path(
            "docs/generated/telegram_navigation_inventory.md"
        ).read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            generated = Path(directory) / "inventory.md"
            result = self._run_inventory("--markdown", str(generated))
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertEqual(expected, generated.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
