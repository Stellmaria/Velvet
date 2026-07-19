from __future__ import annotations

import subprocess
import sys
import unittest


class ArchitectureLayoutInventoryTests(unittest.TestCase):
    def test_inventory_matches_current_tree(self) -> None:
        subprocess.run(
            [
                sys.executable,
                "scripts/inventory_architecture_layout.py",
                "--check",
                "--label",
                "p3c-characters-stories-presentation",
            ],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
