from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_INVENTORY = ROOT / "docs" / "package_architecture_inventory.json"
SHARED_INVENTORY = ROOT / "docs" / "shared_contract_inventory.json"
PACKAGE_TEST = ROOT / "tests" / "test_package_architecture_inventory.py"

SNAPSHOT_MARKER = "## Срез feature-ветки AUF от 4 августа 2026 года"
CANONICAL_DOCS = (
    ROOT / "docs" / "development_status.md",
    ROOT / "docs" / "project_memory.md",
    ROOT / "docs" / "ARCHITECTURE_AUDIT.md",
)


def _replace_one(text: str, pattern: str, replacement: str, *, label: str) -> str:
    updated, count = re.subn(pattern, replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"Не удалось синхронизировать {label}: совпадений {count}")
    return updated


def _sync_package_test(package: dict[str, object]) -> None:
    text = PACKAGE_TEST.read_text(encoding="utf-8")

    scalar_fields = {
        "production_module_count": int(package["production_module_count"]),
        "production_loc": int(package["production_loc"]),
        "root_module_count": int(package["root_module_count"]),
        "router_count": int(package["router_count"]),
        "repository_module_count": int(package["repository_module_count"]),
        "violation_count": int(package["violation_count"]),
    }
    for field, value in scalar_fields.items():
        text = _replace_one(
            text,
            rf'self\.assertEqual\([\d_]+, self\.inventory\["{field}"\]\)',
            f'self.assertEqual({value:_}, self.inventory["{field}"])',
            label=field,
        )

    shared = package["shared_contract_summary"]
    if not isinstance(shared, dict):
        raise RuntimeError("shared_contract_summary отсутствует")
    shared_fields = (
        "production_python_files",
        "function_count",
        "private_contract_access_count",
        "blocking_private_contract_access_count",
        "exact_duplicate_group_count",
        "normalized_duplicate_group_count",
        "semantic_near_duplicate_group_count",
    )
    for field in shared_fields:
        value = int(shared[field])
        text = _replace_one(
            text,
            rf'self\.assertEqual\([\d_]+, shared\["{field}"\]\)',
            f'self.assertEqual({value:_}, shared["{field}"])',
            label=f"shared.{field}",
        )

    markdown_values = {
        "Production modules": int(package["production_module_count"]),
        "Production LOC": int(package["production_loc"]),
        "Startup installer stages": len(package["installer_graph"]),
        "Registered package violations": int(package["violation_count"]),
        "Registered exemptions": int(package["violation_count"]),
    }
    for label, value in markdown_values.items():
        text = _replace_one(
            text,
            rf'"{re.escape(label)}: \*\*[\d]+\*\*"',
            f'"{label}: **{value}**"',
            label=f"markdown {label}",
        )

    PACKAGE_TEST.write_text(text, encoding="utf-8")


def _snapshot(shared: dict[str, object], package: dict[str, object]) -> str:
    return (
        f"{SNAPSHOT_MARKER}\n\n"
        "Этот блок фиксирует воспроизводимые числа текущей feature-ветки PR #590. "
        "Он не означает merge, rollout или закрытие архитектурного долга.\n\n"
        f"- production Python files: **{int(shared['production_python_files'])}**;\n"
        f"- inventoried functions: **{int(shared['function_count'])}**;\n"
        f"- registered transitional private accesses: "
        f"**{int(shared['private_contract_access_count'])}**;\n"
        f"- blocking known private contracts: "
        f"**{int(shared['blocking_private_contract_access_count'])}**;\n"
        f"- package production modules: **{int(package['production_module_count'])}**;\n"
        f"- package production LOC: **{int(package['production_loc'])}**;\n"
        f"- registered package architecture fingerprints: "
        f"**{int(package['violation_count'])}**.\n\n"
        "Переходные media delivery и provider-routing слои по-прежнему требуют "
        "burn-down в #457 и #459.\n"
    )


def _sync_canonical_docs(shared: dict[str, object], package: dict[str, object]) -> None:
    snapshot = _snapshot(shared, package)
    for path in CANONICAL_DOCS:
        text = path.read_text(encoding="utf-8").rstrip()
        if SNAPSHOT_MARKER in text:
            text = text.split(SNAPSHOT_MARKER, 1)[0].rstrip()
        path.write_text(f"{text}\n\n{snapshot}\n", encoding="utf-8")


def main() -> None:
    package = json.loads(PACKAGE_INVENTORY.read_text(encoding="utf-8"))
    shared = json.loads(SHARED_INVENTORY.read_text(encoding="utf-8"))
    _sync_package_test(package)
    _sync_canonical_docs(shared, package)


if __name__ == "__main__":
    main()
