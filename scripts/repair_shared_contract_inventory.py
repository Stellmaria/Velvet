from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "shared_contract_inventory.py"
PATTERN = re.compile(
    r"annotation\s*=\s*self\.visit\(\s*node\.annotation\s*\)\s*,?"
)
NEW = (
    "annotation=(\n"
    "                self.visit(node.annotation)\n"
    "                if node.annotation is not None\n"
    "                else None\n"
    "            ),"
)


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    if "if node.annotation is not None" in source:
        print("AST argument annotation normalization is already repaired.")
        return 0
    updated, count = PATTERN.subn(NEW, source, count=1)
    if count:
        TARGET.write_text(updated, encoding="utf-8")
        print("Repaired optional AST argument annotation normalization.")
        return 0
    start = source.find("def visit_arg")
    excerpt = source[start : start + 400] if start >= 0 else "visit_arg not found"
    raise RuntimeError(
        "shared contract inventory repair target is missing:\n" + excerpt
    )


if __name__ == "__main__":
    raise SystemExit(main())
