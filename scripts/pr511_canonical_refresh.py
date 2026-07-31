from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> None:
    subprocess.run(args, cwd=ROOT, check=True)


def replace(text: str, old: str, new: str, *, label: str) -> str:
    if old in text:
        return text.replace(old, new)
    if new in text:
        return text
    raise RuntimeError(f"canonical replacement missing: {label}")


def update_navigation() -> None:
    run(
        sys.executable,
        "scripts/telegram_navigation_inventory.py",
        "--root",
        "velvet_bot",
        "--markdown",
        "docs/generated/telegram_navigation_inventory.md",
    )


def update_status() -> None:
    path = ROOT / "docs/development_status.md"
    text = path.read_text(encoding="utf-8")
    pairs = (
        ("production modules package-wide: **604**", "production modules package-wide: **631**"),
        ("production LOC: **128 870**", "production LOC: **136 683**"),
        ("repository modules: **35**", "repository modules: **41**"),
        ("infrastructure PostgreSQL adapters: **1**", "infrastructure PostgreSQL adapters: **7**"),
        ("startup installer stages: **27**", "startup installer stages: **28**"),
        ("registered package architecture fingerprints: **518**", "registered package architecture fingerprints: **546**"),
        ("mandatory package exemptions: **518**", "mandatory package exemptions: **546**"),
        ("production Python files в shared-contract inventory: **596**", "production Python files в shared-contract inventory: **631**"),
        ("функций inventoried: **3306**", "функций inventoried: **3597**"),
        ("registered private cross-module debt: **136**", "registered private cross-module debt: **182**"),
        ("exact / normalized / semantic duplicate groups: **55 / 92 / 9**", "exact / normalized / semantic duplicate groups: **62 / 97 / 9**"),
        ("Telegram navigation scan: **604 Python files**, **1024 inline buttons**, **0 violations**", "Telegram navigation scan: **631 Python files**, **1049 inline buttons**, **0 violations**"),
        ("518 package fingerprints", "546 package fingerprints"),
    )
    for old, new in pairs:
        text = replace(text, old, new, label=old)
    path.write_text(text, encoding="utf-8")


def update_memory() -> None:
    path = ROOT / "docs/project_memory.md"
    text = path.read_text(encoding="utf-8")
    pairs = (
        ("startup graph из 27 side-effect installers", "startup graph из 28 side-effect installers"),
        ("518 registered package fingerprints", "546 registered package fingerprints"),
        ("repository inventory: 35 modules, 34 domain + 1 infrastructure", "repository inventory: 41 modules, 34 domain + 7 infrastructure"),
        ("broad exception boundaries: 76", "broad exception boundaries: 102"),
        ("approved boundaries: 76", "approved boundaries: 102"),
        ("callback handlers: 98", "callback handlers: 132"),
        ("repository modules: 35", "repository modules: 41"),
        ("infrastructure adapters: 1", "infrastructure adapters: 7"),
        ("- 604 production modules;", "- 631 production modules;"),
        ("- 128 870 LOC;", "- 136 683 LOC;"),
        ("- 27 ordered startup installer stages;", "- 28 ordered startup installer stages;"),
        ("- 518 registered file/category fingerprints;", "- 546 registered file/category fingerprints;"),
        ("- 518 complete exemptions;", "- 546 complete exemptions;"),
        ("- 596 production Python files;", "- 631 production Python files;"),
        ("- 3306 functions;", "- 3597 functions;"),
        ("- 136 registered private cross-module accesses;", "- 182 registered private cross-module accesses;"),
        ("- 55 exact, 92 normalized и 9 semantic duplicate groups.", "- 62 exact, 97 normalized и 9 semantic duplicate groups."),
        ("136 accesses остаются", "182 accesses остаются"),
    )
    for old, new in pairs:
        text = replace(text, old, new, label=old)
    path.write_text(text, encoding="utf-8")


def update_audit() -> None:
    package = json.loads(
        (ROOT / "docs/package_architecture_inventory.json").read_text(encoding="utf-8")
    )
    layers = package["layer_counts"]
    layer_line = "- layer counts: " + ", ".join(
        f"{name} {int(value)}" for name, value in layers.items()
    ) + ";"

    path = ROOT / "docs/ARCHITECTURE_AUDIT.md"
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(
        r"- layer counts: [^\n]+;",
        layer_line,
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"architecture layer line count={count}")
    pairs = (
        ("все 604 production Python modules", "все 631 production Python modules"),
        ("production modules: **604**", "production modules: **631**"),
        ("production LOC: **128 870**", "production LOC: **136 683**"),
        ("startup installer stages: **27**", "startup installer stages: **28**"),
        ("registered file/category fingerprints: **518**", "registered file/category fingerprints: **546**"),
        ("mandatory exemptions: **518**", "mandatory exemptions: **546**"),
        ("repository modules: **35**", "repository modules: **41**"),
        ("infrastructure PostgreSQL adapters: **1**", "infrastructure PostgreSQL adapters: **7**"),
        ("production Python files: **596**", "production Python files: **631**"),
        ("functions inventoried: **3306**", "functions inventoried: **3597**"),
        ("registered private cross-module accesses: **136**", "registered private cross-module accesses: **182**"),
        ("exact duplicate groups: **55**", "exact duplicate groups: **62**"),
        ("normalized near-duplicate groups: **92**", "normalized near-duplicate groups: **97**"),
        ("136 accesses остаются", "182 accesses остаются"),
        ("scanned Python files: **604**", "scanned Python files: **631**"),
        ("inline buttons: **1024**", "inline buttons: **1049**"),
        ("broad exception boundaries: 76", "broad exception boundaries: 102"),
        ("approved boundaries: 76", "approved boundaries: 102"),
        ("callback handlers: 98", "callback handlers: 132"),
        ("bootstrap и 52 composition modules/installers", "bootstrap и 63 composition modules/installers"),
        ("14 transport-neutral use-case modules", "20 transport-neutral use-case modules"),
        ("175 domain modules и 34 repositories", "176 domain modules и 34 repositories"),
        ("17 PostgreSQL/provider/Telegram/filesystem adapters", "25 PostgreSQL/provider/Telegram/filesystem adapters"),
        ("213 Telegram presentation modules", "214 Telegram presentation modules"),
        ("всего **27 side-effect installation stages**", "всего **28 side-effect installation stages**"),
        ("существующие 518 fingerprints", "существующие 546 fingerprints"),
    )
    for old, new in pairs:
        text = replace(text, old, new, label=old)
    path.write_text(text, encoding="utf-8")


def update_contract_test() -> None:
    path = ROOT / "tests/test_canonical_docs_sync.py"
    text = path.read_text(encoding="utf-8")
    pairs = (
        ('self.assertIn("repository modules: 35", self.memory)', 'self.assertIn("repository modules: 41", self.memory)'),
        ('self.assertIn("Python files scanned: **630**", self.navigation)', 'self.assertIn("Python files scanned: **631**", self.navigation)'),
        ('self.assertIn("27 side-effect installation stages", self.audit)', 'self.assertIn("28 side-effect installation stages", self.audit)'),
    )
    for old, new in pairs:
        text = replace(text, old, new, label=old)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    update_navigation()
    update_status()
    update_memory()
    update_audit()
    update_contract_test()
    run(sys.executable, "-m", "compileall", "-q", "tests")


if __name__ == "__main__":
    main()
