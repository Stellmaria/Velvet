from __future__ import annotations

import ast
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ORIGINAL_SCRIPT = ROOT / "scripts" / "inventory_package_architecture.py"
FAST_SCRIPT = ROOT / "scripts" / "inventory_package_architecture_fast.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


class PackageArchitectureFastOwnerTests(unittest.TestCase):
    def test_fast_owner_matches_original_narrowest_span_semantics(self) -> None:
        original = _load(ORIGINAL_SCRIPT, "_test_original_package_inventory")
        fast = _load(FAST_SCRIPT, "_test_fast_package_inventory")
        tree = ast.parse(
            """
value = 1
class Outer:
    marker = 2
    def method(self):
        before = 3
        def nested():
            return 4
        return nested()

def standalone():
    return 5
""".lstrip()
        )

        for line in range(1, 12):
            with self.subTest(line=line):
                self.assertEqual(original._owner(tree, line), fast._fast_owner(tree, line))

    def test_fast_owner_reindexes_when_module_changes(self) -> None:
        fast = _load(FAST_SCRIPT, "_test_fast_package_inventory_reindex")
        first = ast.parse("def first():\n    return 1\n")
        second = ast.parse("class Second:\n    value = 2\n")

        self.assertEqual("first", fast._fast_owner(first, 2))
        self.assertEqual("Second", fast._fast_owner(second, 2))
        self.assertEqual("first", fast._fast_owner(first, 2))


if __name__ == "__main__":
    unittest.main()
