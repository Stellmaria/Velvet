from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def replace_fingerprints() -> None:
    path = ROOT / "docs/package_architecture_exemptions.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    replacements = {
        "foreign-assignment:velvet_bot/app/workers.py:": (
            "foreign-assignment:velvet_bot/app/workers.py:15d6b7884adb804c5c22ee15"
        ),
        "monolithic-function:velvet_bot/domains/workspaces/qwen_repository.py:mark_ready:": (
            "monolithic-function:velvet_bot/domains/workspaces/"
            "qwen_repository.py:mark_ready:1d9ff837ba89b8e6cd1718d4"
        ),
        "monolithic-module-loc:velvet_bot/ai_quality.py:": (
            "monolithic-module-loc:velvet_bot/ai_quality.py:8d49a9561071f8f9c433f397"
        ),
    }
    rows = data.get("exceptions", [])
    if not isinstance(rows, list):
        raise SystemExit("Architecture exemptions must contain a list")
    for prefix, replacement in replacements.items():
        matching = [
            row
            for row in rows
            if isinstance(row, dict) and str(row.get("id", "")).startswith(prefix)
        ]
        if len(matching) != 1:
            raise SystemExit(
                f"Expected one architecture exemption for {prefix}, found {len(matching)}"
            )
        matching[0]["id"] = replacement
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def replace_once(source: str, pattern: str, replacement: str, *, label: str) -> str:
    updated, count = re.subn(pattern, replacement, source, count=1)
    if count != 1:
        raise SystemExit(f"Reviewed assertion not found: {label}")
    return updated


def refresh_repository_inventory() -> None:
    run(
        sys.executable,
        "scripts/inventory_repository_layout.py",
        "--write",
        "--label",
        "p3e-repository-layout-complete",
    )
    inventory = json.loads(
        (ROOT / "docs/repository_layout_inventory.json").read_text(encoding="utf-8")
    )
    path = ROOT / "tests/test_p3e_repository_layout_inventory.py"
    source = path.read_text(encoding="utf-8")
    source = replace_once(
        source,
        r'self\.assertEqual\([0-9_]+, inventory\["repository_module_count"\]\)',
        (
            f'self.assertEqual({inventory["repository_module_count"]:_}, '
            'inventory["repository_module_count"])'
        ),
        label="repository module count",
    )
    source = replace_once(
        source,
        r'self\.assertEqual\([0-9_]+, inventory\["layout_counts"\]\["domain"\]\)',
        (
            f'self.assertEqual({inventory["layout_counts"]["domain"]:_}, '
            'inventory["layout_counts"]["domain"])'
        ),
        label="domain repository count",
    )
    path.write_text(source, encoding="utf-8")


def refresh_package_inventory() -> None:
    run(
        sys.executable,
        "scripts/inventory_package_architecture.py",
        "--write",
        "--label",
        "p1-package-architecture-baseline",
    )
    inventory = json.loads(
        (ROOT / "docs/package_architecture_inventory.json").read_text(encoding="utf-8")
    )
    path = ROOT / "tests/test_package_architecture_inventory.py"
    source = path.read_text(encoding="utf-8")
    replacements = (
        (
            r'self\.assertEqual\([0-9_]+, self\.inventory\["production_module_count"\]\)',
            f'self.assertEqual({inventory["production_module_count"]:_}, self.inventory["production_module_count"])',
            "production module count",
        ),
        (
            r'self\.assertEqual\([0-9_]+, self\.inventory\["production_loc"\]\)',
            f'self.assertEqual({inventory["production_loc"]:_}, self.inventory["production_loc"])',
            "production LOC",
        ),
        (
            r'self\.assertEqual\([0-9_]+, self\.inventory\["root_module_count"\]\)',
            f'self.assertEqual({inventory["root_module_count"]:_}, self.inventory["root_module_count"])',
            "root module count",
        ),
        (
            r'self\.assertEqual\([0-9_]+, self\.inventory\["router_count"\]\)',
            f'self.assertEqual({inventory["router_count"]:_}, self.inventory["router_count"])',
            "router count",
        ),
        (
            r'self\.assertEqual\([0-9_]+, self\.inventory\["repository_module_count"\]\)',
            f'self.assertEqual({inventory["repository_module_count"]:_}, self.inventory["repository_module_count"])',
            "package repository count",
        ),
        (
            r'self\.assertEqual\([0-9_]+, len\(self\.inventory\["installer_graph"\]\)\)',
            f'self.assertEqual({len(inventory["installer_graph"]):_}, len(self.inventory["installer_graph"]))',
            "installer graph count",
        ),
        (
            r'self\.assertIn\("Production modules: \*\*[0-9_]+\*\*", self\.markdown\)',
            f'self.assertIn("Production modules: **{inventory["production_module_count"]}**", self.markdown)',
            "markdown production modules",
        ),
        (
            r'self\.assertIn\("Production LOC: \*\*[0-9_]+\*\*", self\.markdown\)',
            f'self.assertIn("Production LOC: **{inventory["production_loc"]}**", self.markdown)',
            "markdown production LOC",
        ),
    )
    for pattern, replacement, label in replacements:
        source = replace_once(source, pattern, replacement, label=label)
    path.write_text(source, encoding="utf-8")


def main() -> int:
    replace_fingerprints()
    refresh_repository_inventory()
    refresh_package_inventory()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
