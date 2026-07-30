from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "scripts" / "shared_contract_inventory.py"
OLD = "annotation=self.visit(node.annotation),"
NEW = (
    "annotation=(\n"
    "                self.visit(node.annotation)\n"
    "                if node.annotation is not None\n"
    "                else None\n"
    "            ),"
)


def main() -> int:
    source = TARGET.read_text(encoding="utf-8")
    if OLD in source:
        TARGET.write_text(source.replace(OLD, NEW, 1), encoding="utf-8")
        print("Repaired optional AST argument annotation normalization.")
        return 0
    if "if node.annotation is not None" in source:
        print("AST argument annotation normalization is already repaired.")
        return 0
    raise RuntimeError("shared contract inventory repair target is missing")


if __name__ == "__main__":
    raise SystemExit(main())
