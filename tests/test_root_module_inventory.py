from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "inventory_root_modules.py"
DOC = ROOT / "docs" / "root_module_inventory.md"


class RootModuleInventoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--check", "--json"],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if completed.returncode:
            raise AssertionError(
                "Root module inventory contract failed:\n"
                + completed.stderr
                + "\n"
                + completed.stdout
            )
        cls.inventory = json.loads(completed.stdout)

    def test_every_root_module_is_classified(self) -> None:
        entries = self.inventory["entries"]
        self.assertEqual(self.inventory["root_module_count"], len(entries))
        self.assertEqual(0, self.inventory["unclassified_count"])
        self.assertTrue(entries)
        for entry in entries:
            with self.subTest(path=entry["path"]):
                self.assertIn(
                    entry["category"],
                    {
                        "domain",
                        "application",
                        "infrastructure",
                        "presentation",
                        "worker",
                        "public facade",
                    },
                )
                self.assertTrue(entry["classification_rule"])
                self.assertIsInstance(entry["consumers"], list)
                self.assertIsInstance(entry["side_effects"], list)

    def test_public_facades_have_explicit_contracts(self) -> None:
        facade_entries = [
            entry
            for entry in self.inventory["entries"]
            if entry["category"] == "public facade"
        ]
        self.assertTrue(facade_entries)
        for entry in facade_entries:
            with self.subTest(path=entry["path"]):
                self.assertTrue(entry["public_contract"])

    def test_human_inventory_matches_machine_baseline(self) -> None:
        text = DOC.read_text(encoding="utf-8")
        self.assertIn(
            f"корневых модулей: **{self.inventory['root_module_count']}**",
            text,
        )
        self.assertIn(
            f"`{self.inventory['root_module_name_sha256']}`",
            text,
        )
        for category, count in self.inventory["category_counts"].items():
            self.assertIn(f"`{category}`: **{count}**", text)


if __name__ == "__main__":
    unittest.main()
