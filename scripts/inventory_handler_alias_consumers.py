from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"
HANDLERS = PACKAGE / "handlers"
PREFIX = "velvet_bot.handlers"
ALIAS_MARKER = "P3_COMPAT_MODULE_ALIAS"
JSON_PATH = ROOT / "docs" / "handler_alias_consumer_inventory.json"
MARKDOWN_PATH = ROOT / "docs" / "handler_alias_consumer_inventory.md"
SKIP_PARTS = {
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    "runtime",
    "logs",
    "data",
    "backups",
}


def _alias_modules() -> dict[str, str]:
    aliases: dict[str, str] = {}
    for path in sorted(HANDLERS.glob("*.py")):
        if path.name == "__init__.py":
            continue
        source = path.read_text(encoding="utf-8")
        if ALIAS_MARKER not in source:
            continue
        module = f"{PREFIX}.{path.stem}"
        target = ""
        tree = ast.parse(source, filename=str(path))
        for node in tree.body:
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == ALIAS_MARKER
            ):
                target = str(ast.literal_eval(node.value))
                break
        aliases[module] = target
    return aliases


def _constant_module(value: str) -> str | None:
    if not value.startswith(f"{PREFIX}."):
        return None
    parts = value.split(".")
    if len(parts) < 3 or not parts[2]:
        return None
    return ".".join(parts[:3])


def _references(path: Path) -> list[dict[str, Any]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rows: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = _constant_module(alias.name)
                if module:
                    rows.append({"kind": "import", "module": module, "line": node.lineno})
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == PREFIX:
                for alias in node.names:
                    rows.append(
                        {
                            "kind": "from-package",
                            "module": f"{PREFIX}.{alias.name}",
                            "line": node.lineno,
                        }
                    )
            else:
                legacy = _constant_module(module)
                if legacy:
                    rows.append(
                        {"kind": "from-import", "module": legacy, "line": node.lineno}
                    )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            legacy = _constant_module(node.value)
            if legacy:
                rows.append(
                    {"kind": "literal-reference", "module": legacy, "line": node.lineno}
                )
        elif isinstance(node, ast.JoinedStr):
            text = "".join(
                part.value
                for part in node.values
                if isinstance(part, ast.Constant) and isinstance(part.value, str)
            )
            if PREFIX in text:
                rows.append(
                    {
                        "kind": "dynamic-prefix-reference",
                        "module": PREFIX,
                        "line": getattr(node, "lineno", 0),
                    }
                )
    unique = {
        (str(row["kind"]), str(row["module"]), int(row["line"])): row for row in rows
    }
    return sorted(unique.values(), key=lambda row: (int(row["line"]), str(row["module"])))


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    for path in ROOT.rglob("*.py"):
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if HANDLERS in path.parents:
            continue
        paths.append(path)
    return sorted(paths)


def build_inventory(*, label: str = "working-tree") -> dict[str, Any]:
    aliases = _alias_modules()
    consumers: list[dict[str, Any]] = []
    referenced: set[str] = set()
    missing: set[str] = set()
    dynamic_prefix_count = 0
    for path in _candidate_paths():
        refs = _references(path)
        if not refs:
            continue
        for ref in refs:
            module = str(ref["module"])
            if module == PREFIX:
                dynamic_prefix_count += 1
            elif module in aliases:
                referenced.add(module)
            else:
                missing.add(module)
        consumers.append(
            {"path": path.relative_to(ROOT).as_posix(), "references": refs}
        )
    unreferenced = sorted(set(aliases) - referenced)
    return {
        "schema_version": 1,
        "generated_from": label,
        "alias_file_count": len(aliases),
        "consumer_file_count": len(consumers),
        "reference_count": sum(len(item["references"]) for item in consumers),
        "referenced_alias_count": len(referenced),
        "unreferenced_alias_count": len(unreferenced),
        "dynamic_prefix_reference_count": dynamic_prefix_count,
        "missing_alias_reference_count": len(missing),
        "missing_alias_references": sorted(missing),
        "aliases": [
            {
                "module": module,
                "target": aliases[module],
                "referenced": module in referenced,
            }
            for module in sorted(aliases)
        ],
        "unreferenced_aliases": unreferenced,
        "consumers": consumers,
        "next_slice": {
            "phase": "P3D",
            "target": "retire the next compatibility alias group",
            "strategy": "migrate tests to canonical modules, then delete only aliases with no repository references",
        },
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Инвентаризация consumers handler aliases",
        "",
        "Машинный срез оставшегося compatibility API `velvet_bot.handlers.*` после закрытия production consumers.",
        "",
        "## Сводка",
        "",
        f"- alias-файлов: **{data['alias_file_count']}**;",
        f"- файлов-consumers: **{data['consumer_file_count']}**;",
        f"- references: **{data['reference_count']}**;",
        f"- aliases с references: **{data['referenced_alias_count']}**;",
        f"- aliases без references: **{data['unreferenced_alias_count']}**;",
        f"- динамических prefix references: **{data['dynamic_prefix_reference_count']}**;",
        f"- references на уже отсутствующие aliases: **{data['missing_alias_reference_count']}**.",
        "",
        "## Alias status",
        "",
    ]
    for item in data["aliases"]:
        marker = "используется" if item["referenced"] else "без repository consumers"
        lines.append(f"- `{item['module']}` → `{item['target']}`: {marker}.")
    lines.extend(["", "## Consumers", ""])
    for consumer in data["consumers"]:
        lines.append(f"### `{consumer['path']}`")
        lines.append("")
        for ref in consumer["references"]:
            lines.append(
                f"- line {ref['line']}: `{ref['module']}` ({ref['kind']})."
            )
        lines.append("")
    next_slice = data["next_slice"]
    lines.extend(
        [
            "## Следующий срез",
            "",
            f"- фаза: **{next_slice['phase']}**;",
            f"- цель: **{next_slice['target']}**;",
            f"- стратегия: {next_slice['strategy']}.",
            "",
            "## Правило обновления",
            "",
            "```bash",
            "python scripts/inventory_handler_alias_consumers.py --write --label <phase>",
            "python scripts/inventory_handler_alias_consumers.py --check --label <phase>",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _write(data: dict[str, Any]) -> None:
    JSON_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    MARKDOWN_PATH.write_text(render_markdown(data), encoding="utf-8")


def _check(data: dict[str, Any]) -> None:
    expected_json = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    expected_markdown = render_markdown(data)
    if not JSON_PATH.is_file() or JSON_PATH.read_text(encoding="utf-8") != expected_json:
        raise SystemExit("handler_alias_consumer_inventory.json устарел")
    if not MARKDOWN_PATH.is_file() or MARKDOWN_PATH.read_text(encoding="utf-8") != expected_markdown:
        raise SystemExit("handler_alias_consumer_inventory.md устарел")
    if data["missing_alias_reference_count"]:
        raise SystemExit(
            "Обнаружены references на удалённые handler aliases: "
            + ", ".join(data["missing_alias_references"])
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="working-tree")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    data = build_inventory(label=args.label)
    if args.write:
        _write(data)
    if args.check:
        _check(data)
    if not args.write and not args.check:
        print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
