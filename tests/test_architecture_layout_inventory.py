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
                "manager-large-files-character-tags",
            ],
            check=True,
        )


if __name__ == "__main__":
    unittest.main()
