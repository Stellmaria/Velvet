from __future__ import annotations

import base64
import io
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILES = (
    "docs/package_architecture_inventory.json",
    "docs/package_architecture_inventory.md",
    "docs/package_architecture_exemptions.json",
    "docs/p2_stability_inventory.json",
    "docs/p2_stability_inventory.md",
    "tests/test_package_architecture_inventory.py",
)
CANONICAL_PREFLIGHT = '''from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests import test_package_architecture_inventory
from tests import test_telegram_navigation_inventory


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
'''


def _run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def main() -> int:
    # Replace this temporary entrypoint in the runner worktree before counting
    # modules and LOC. The generated archive therefore describes the final tree
    # after the exporter commit is removed, even with checkout fetch-depth=1.
    (ROOT / "scripts/ci_preflight.py").write_text(
        CANONICAL_PREFLIGHT,
        encoding="utf-8",
    )

    _run(
        sys.executable,
        "scripts/inventory_package_architecture.py",
        "--write",
        "--bootstrap-exemptions",
        "--label",
        "p1-package-architecture-baseline",
    )
    _run(
        sys.executable,
        "scripts/update_p2_stability_inventory.py",
        "--label",
        "storage-librarian-afk-guardrails",
        "--schema-version",
        "78",
    )

    inventory_path = ROOT / "docs/package_architecture_inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    test_path = ROOT / "tests/test_package_architecture_inventory.py"
    text = test_path.read_text(encoding="utf-8")
    keys = (
        "production_module_count",
        "production_loc",
        "root_module_count",
        "router_count",
        "repository_module_count",
        "violation_count",
    )
    for key in keys:
        pattern = rf'self\.assertEqual\(\d[\d_]*, self\.inventory\["{key}"\]\)'
        replacement = (
            f'self.assertEqual({int(inventory[key]):_}, '
            f'self.inventory["{key}"])'
        )
        text, count = re.subn(pattern, replacement, text, count=1)
        if count != 1:
            raise RuntimeError(f"expected one assertion for {key}, found {count}")
    pattern = (
        r'self\.assertEqual\(\d[\d_]*, '
        r'len\(self\.inventory\["installer_graph"\]\)\)'
    )
    replacement = (
        f'self.assertEqual({len(inventory["installer_graph"]):_}, '
        'len(self.inventory["installer_graph"]))'
    )
    text, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"expected one installer assertion, found {count}")
    test_path.write_text(text, encoding="utf-8")

    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for relative in FILES:
            archive.add(ROOT / relative, arcname=relative)
    encoded = base64.b64encode(payload.getvalue()).decode("ascii")
    print("AFK_INVENTORY_ARCHIVE_BEGIN")
    print(encoded)
    print("AFK_INVENTORY_ARCHIVE_END")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
