from __future__ import annotations

import base64
import io
import subprocess
import sys
import tarfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_PATHS = (
    Path("docs/package_architecture_inventory.json"),
    Path("docs/package_architecture_inventory.md"),
    Path("docs/package_architecture_exemptions.json"),
    Path("docs/generated/telegram_navigation_inventory.md"),
)


class Pr484InventoryCaptureTests(unittest.TestCase):
    def test_regenerate_and_emit_merged_inventories(self) -> None:
        package = subprocess.run(
            [
                sys.executable,
                "scripts/inventory_package_architecture.py",
                "--label",
                "p1-package-architecture-baseline",
                "--write",
                "--bootstrap-exemptions",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=180,
        )
        self.assertEqual(0, package.returncode, package.stdout + package.stderr)

        navigation = subprocess.run(
            [
                sys.executable,
                "scripts/telegram_navigation_inventory.py",
                "--root",
                "velvet_bot",
                "--markdown",
                "docs/generated/telegram_navigation_inventory.md",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            timeout=180,
        )
        self.assertEqual(
            0,
            navigation.returncode,
            navigation.stdout + navigation.stderr,
        )

        payload = io.BytesIO()
        with tarfile.open(fileobj=payload, mode="w:gz") as archive:
            for relative in ARTIFACT_PATHS:
                archive.add(ROOT / relative, arcname=relative.as_posix())

        print("PR484_INVENTORY_TGZ_BASE64_BEGIN")
        print(base64.b64encode(payload.getvalue()).decode("ascii"))
        print("PR484_INVENTORY_TGZ_BASE64_END")


if __name__ == "__main__":
    unittest.main()
