from __future__ import annotations

import unittest
from pathlib import Path

from tests import test_package_architecture_inventory
from tests import test_telegram_navigation_inventory


ROOT = Path(__file__).resolve().parents[1]
FAST_PACKAGE_INVENTORY = ROOT / "scripts" / "inventory_package_architecture_fast.py"


def build_suite() -> unittest.TestSuite:
    test_package_architecture_inventory.SCRIPT = FAST_PACKAGE_INVENTORY
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromModule(test_package_architecture_inventory))
    suite.addTests(loader.loadTestsFromModule(test_telegram_navigation_inventory))
    return suite


def main() -> int:
    result = unittest.TextTestRunner(
        verbosity=2,
        failfast=True,
        durations=20,
    ).run(build_suite())
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
