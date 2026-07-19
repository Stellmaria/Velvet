from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"
LEGACY_PACKAGE = PACKAGE / "handlers"
PREFIX = "velvet_bot.handlers"
JSON_PATH = ROOT / "docs" / "legacy_handler_consumer_inventory.json"
MARKDOWN_PATH = ROOT / "docs" / "legacy_handler_consumer_inventory.md"
CLEANED_PATHS = frozenset(
    {
        "velvet_bot/presentation/telegram/routers/characters/uncategorized.py",
        "velvet_bot/presentation/telegram/routers/stories/management.py",
    }
)


def _legacy_imports(path: Path) -> list[dict[str, Any]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    rows: list[dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == PREFIX:
                for alias in node.names:
                    rows.append(
                        {
                            "kind": "import",
                            "module": f"{PREFIX}.{alias.name}",
                            "names": [alias.asname or alias.name],
                            "line": node.lineno,
                        }
                    )
            elif module.startswith(f"{PREFIX}."):
                rows.append(
                    {
                        "kind": "import",
                        "module": module,
                        "names": sorted(alias.name for alias in node.names),
                        "line": node.lineno,
                    }
                )
            elif module == "velvet_bot":
                for alias in node.names:
                    if alias.name == "handlers":
                        rows.append(
                            {
                                "kind": "import",
                                "module": PREFIX,
                                "names": [alias.asname or alias.name],
                                "line": node.lineno,
                            }
                        )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == PREFIX or alias.name.startswith(f"{PREFIX}."):
                    rows.append(
                        {
                            "kind": "import",
                            "module": alias.name,
                            "names": [alias.asname or alias.name],
                            "line": node.lineno,
                        }
                    )
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value.startswith(f"{PREFIX}.")
        ):
            rows.append(
                {
                    "kind": "dynamic-reference",
                    "module": node.value,
                    "names": [],
                    "line": getattr(node, "lineno", 0),
                }
            )

    unique: dict[tuple[str, str, int, tuple[str, ...]], dict[str, Any]] = {}
    for row in rows:
        key = (
            str(row["kind"]),
            str(row["module"]),
            int(row["line"]),
            tuple(str(name) for name in row["names"]),
        )
        unique[key] = row
    return sorted(
        unique.values(),
        key=lambda row: (int(row["line"]), str(row["module"]), str(row["kind"])),
    )


def build_inventory(*, label: str = "working-tree") -> dict[str, Any]:
    consumers: list[dict[str, Any]] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if LEGACY_PACKAGE in path.parents:
            continue
        imports = _legacy_imports(path)
        if imports:
            consumers.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "imports": imports,
                }
            )

    modules = sorted(
        {
            str(item["module"])
            for consumer in consumers
            for item in consumer["imports"]
        }
    )
    return {
        "schema_version": 1,
        "generated_from": label,
        "consumer_file_count": len(consumers),
        "legacy_reference_count": sum(
            len(consumer["imports"]) for consumer in consumers
        ),
        "legacy_module_count": len(modules),
        "legacy_modules": modules,
        "consumers": consumers,
        "cleaned_paths": sorted(CLEANED_PATHS),
        "next_slice": {
            "phase": "P3D",
            "target": "retire the next reviewed legacy consumer group",
            "strategy": "move shared helpers to public contracts before deleting aliases",
        },
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Инвентаризация consumers старых handler paths",
        "",
        "Машинный baseline production-кода, который ещё зависит от "
        "`velvet_bot.handlers.*` aliases.",
        "",
        "## Сводка",
        "",
        f"- файлов-consumers: **{data['consumer_file_count']}**;",
        f"- legacy references: **{data['legacy_reference_count']}**;",
        f"- затронутых legacy modules: **{data['legacy_module_count']}**.",
        "",
        "## Consumers",
        "",
    ]
    for consumer in data["consumers"]:
        lines.append(f"### `{consumer['path']}`")
        lines.append("")
        for item in consumer["imports"]:
            suffix = (
                f"; names: `{', '.join(item['names'])}`" if item["names"] else ""
            )
            lines.append(
                f"- line {item['line']}: `{item['module']}` "
                f"({item['kind']}{suffix})."
            )
        lines.append("")

    lines.extend(["## Уже очищенные paths", ""])
    lines.extend(f"- `{path}`." for path in data["cleaned_paths"])
    next_slice = data["next_slice"]
    lines.extend(
        [
            "",
            "## Следующий срез",
            "",
            f"- фаза: **{next_slice['phase']}**;",
            f"- цель: **{next_slice['target']}**;",
            f"- стратегия: {next_slice['strategy']}.",
            "",
            "## Правило обновления",
            "",
            "```bash",
            "python scripts/inventory_legacy_handler_consumers.py --write --label <phase>",
            "python scripts/inventory_legacy_handler_consumers.py --check --label <phase>",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _write(data: dict[str, Any]) -> None:
    JSON_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MARKDOWN_PATH.write_text(render_markdown(data), encoding="utf-8")


def _check(data: dict[str, Any]) -> None:
    expected_json = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    expected_markdown = render_markdown(data)
    if not JSON_PATH.is_file() or JSON_PATH.read_text(encoding="utf-8") != expected_json:
        raise SystemExit("legacy_handler_consumer_inventory.json устарел")
    if (
        not MARKDOWN_PATH.is_file()
        or MARKDOWN_PATH.read_text(encoding="utf-8") != expected_markdown
    ):
        raise SystemExit("legacy_handler_consumer_inventory.md устарел")

    consumer_paths = {str(item["path"]) for item in data["consumers"]}
    regressions = sorted(CLEANED_PATHS & consumer_paths)
    if regressions:
        raise SystemExit(
            "Legacy handler imports вернулись в очищенные paths: "
            + ", ".join(regressions)
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
