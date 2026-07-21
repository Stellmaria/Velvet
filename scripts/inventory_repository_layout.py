from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"
DOMAINS = PACKAGE / "domains"
CENTRAL_REPOSITORIES = PACKAGE / "repositories"
INFRASTRUCTURE = PACKAGE / "infrastructure"
JSON_PATH = ROOT / "docs" / "repository_layout_inventory.json"
MARKDOWN_PATH = ROOT / "docs" / "repository_layout_inventory.md"
SKIP_PARTS = {
    ".git",
    ".venv",
    ".venv314",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "runtime",
    "logs",
    "data",
    "backups",
}


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT)
    if path.name == "__init__.py":
        return ".".join(relative.parent.parts)
    return ".".join(relative.with_suffix("").parts)


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def _repository_paths() -> list[Path]:
    return sorted(
        path
        for path in PACKAGE.rglob("*.py")
        if path.name != "__init__.py"
        and not _is_skipped(path)
        and "repository" in path.stem.casefold()
    )


def _python_paths() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.py")
        if not _is_skipped(path)
    )


def _layout(path: Path) -> tuple[str, str | None]:
    if path.parent == PACKAGE:
        return "root", None
    if path.parent == CENTRAL_REPOSITORIES:
        return "central", None
    if DOMAINS in path.parents:
        relative = path.relative_to(DOMAINS)
        return "domain", relative.parts[0] if relative.parts else None
    if INFRASTRUCTURE in path.parents:
        return "infrastructure", None
    return "other", None


def _resolve_from_module(path: Path, node: ast.ImportFrom) -> str:
    module = node.module or ""
    if node.level <= 0:
        return module
    current_module = _module_name(path).split(".")
    current = current_module if path.name == "__init__.py" else current_module[:-1]
    keep = max(0, len(current) - (node.level - 1))
    parts = current[:keep]
    if module:
        parts.extend(module.split("."))
    return ".".join(parts)


def _references(path: Path, repository_modules: set[str]) -> list[dict[str, Any]]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError):
        return []
    rows: list[dict[str, Any]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in repository_modules:
                    rows.append(
                        {
                            "kind": "import",
                            "module": alias.name,
                            "line": node.lineno,
                        }
                    )
        elif isinstance(node, ast.ImportFrom):
            base = _resolve_from_module(path, node)
            if base in repository_modules:
                rows.append(
                    {
                        "kind": "from-import",
                        "module": base,
                        "line": node.lineno,
                    }
                )
            for alias in node.names:
                candidate = f"{base}.{alias.name}" if base else alias.name
                if candidate in repository_modules:
                    rows.append(
                        {
                            "kind": "from-package",
                            "module": candidate,
                            "line": node.lineno,
                        }
                    )
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in repository_modules:
                rows.append(
                    {
                        "kind": "literal-reference",
                        "module": node.value,
                        "line": getattr(node, "lineno", 0),
                    }
                )
    unique = {
        (str(row["kind"]), str(row["module"]), int(row["line"])): row
        for row in rows
    }
    return sorted(
        unique.values(),
        key=lambda row: (int(row["line"]), str(row["module"]), str(row["kind"])),
    )


def _root_module_category(path: Path) -> str:
    stem = path.stem.casefold()
    if "repository" in stem:
        return "repository"
    if stem.endswith("_service") or stem.endswith("_services"):
        return "service"
    if stem.endswith("_worker") or stem.endswith("_workers"):
        return "worker"
    if stem.endswith("_runtime"):
        return "runtime"
    if stem.endswith("_report") or stem.endswith("_reports"):
        return "report"
    if stem.endswith("_models") or stem.endswith("_model"):
        return "model"
    return "other"


def _scope(path: Path) -> str:
    if "tests" in path.parts:
        return "test"
    if path.name == "__init__.py":
        return "package_export"
    return "production"


def build_inventory(*, label: str = "working-tree") -> dict[str, Any]:
    repository_paths = _repository_paths()
    repository_modules = {_module_name(path) for path in repository_paths}
    references_by_module: dict[str, list[dict[str, Any]]] = {
        module: [] for module in repository_modules
    }
    for path in _python_paths():
        source_module = _module_name(path)
        for reference in _references(path, repository_modules):
            module = str(reference["module"])
            if source_module == module:
                continue
            references_by_module[module].append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "line": int(reference["line"]),
                    "kind": str(reference["kind"]),
                    "scope": _scope(path),
                }
            )

    rows: list[dict[str, Any]] = []
    for path in repository_paths:
        module = _module_name(path)
        layout, domain = _layout(path)
        references = references_by_module[module]
        production_files = sorted(
            {str(item["path"]) for item in references if item["scope"] == "production"}
        )
        test_files = sorted(
            {str(item["path"]) for item in references if item["scope"] == "test"}
        )
        package_export_files = sorted(
            {
                str(item["path"])
                for item in references
                if item["scope"] == "package_export"
            }
        )
        rows.append(
            {
                "module": module,
                "path": path.relative_to(ROOT).as_posix(),
                "layout": layout,
                "domain": domain,
                "production_consumer_count": len(production_files),
                "test_consumer_count": len(test_files),
                "package_export_count": len(package_export_files),
                "reference_count": len(references),
                "production_consumers": production_files,
                "test_consumers": test_files,
                "package_exports": package_export_files,
            }
        )
    rows.sort(key=lambda item: (str(item["layout"]), str(item["path"])))

    layout_counts = Counter(str(item["layout"]) for item in rows)
    root_modules = sorted(
        path for path in PACKAGE.glob("*.py") if path.name != "__init__.py"
    )
    root_categories = Counter(_root_module_category(path) for path in root_modules)
    candidates = sorted(
        (item for item in rows if item["layout"] in {"root", "central"}),
        key=lambda item: (
            int(item["production_consumer_count"]),
            int(item["test_consumer_count"]),
            int(item["package_export_count"]),
            int(item["reference_count"]),
            str(item["path"]),
        ),
    )[:20]
    unreferenced = [
        item["module"]
        for item in rows
        if int(item["reference_count"]) == 0
    ]
    export_only = [
        item["module"]
        for item in rows
        if int(item["production_consumer_count"]) == 0
        and int(item["test_consumer_count"]) == 0
        and int(item["package_export_count"]) > 0
    ]
    first_candidate = candidates[0] if candidates else None
    if (
        first_candidate is not None
        and int(first_candidate["production_consumer_count"]) == 0
        and int(first_candidate["test_consumer_count"]) == 0
        and int(first_candidate["package_export_count"]) > 0
    ):
        next_target = "retire the first export-only repository module"
        next_strategy = (
            "remove the unused package export and dead module, then update the generated "
            "baseline without creating a replacement facade"
        )
    elif first_candidate is not None and int(first_candidate["reference_count"]) == 0:
        next_target = "retire the first unreferenced repository module"
        next_strategy = (
            "verify dynamic imports remain absent, delete the dead module, and update the "
            "generated baseline without creating a replacement facade"
        )
    else:
        next_target = "migrate the first low-coupling repository module"
        next_strategy = (
            "move one reviewed module to its domain or infrastructure boundary, keep the old path "
            "as a temporary facade, and migrate consumers before deletion"
        )

    return {
        "schema_version": 1,
        "generated_from": label,
        "repository_module_count": len(rows),
        "layout_counts": dict(sorted(layout_counts.items())),
        "root_module_count": len(root_modules),
        "root_module_categories": dict(sorted(root_categories.items())),
        "repository_modules_with_production_consumers": sum(
            1 for item in rows if int(item["production_consumer_count"]) > 0
        ),
        "repository_modules_with_package_exports": sum(
            1 for item in rows if int(item["package_export_count"]) > 0
        ),
        "repository_modules_without_runtime_consumers": sum(
            1 for item in rows if int(item["production_consumer_count"]) == 0
        ),
        "repository_modules_without_references": len(unreferenced),
        "unreferenced_repository_modules": sorted(unreferenced),
        "export_only_repository_modules": sorted(export_only),
        "modules": rows,
        "candidate_modules": candidates,
        "next_slice": {
            "phase": "P3E",
            "target": next_target,
            "candidate": first_candidate["module"] if first_candidate else None,
            "strategy": next_strategy,
        },
    }


def render_markdown(data: dict[str, Any]) -> str:
    counts = data["layout_counts"]
    categories = data["root_module_categories"]
    lines = [
        "# Инвентаризация repository layout Velvet",
        "",
        "Машинный baseline P3E для постепенного выравнивания persistence и корневых модулей без изменения поведения.",
        "",
        "## Сводка",
        "",
        f"- repository-модулей: **{data['repository_module_count']}**;",
        f"- внутри доменов: **{counts.get('domain', 0)}**;",
        f"- в `velvet_bot/repositories`: **{counts.get('central', 0)}**;",
        f"- корневых `*_repository.py`: **{counts.get('root', 0)}**;",
        f"- infrastructure repositories: **{counts.get('infrastructure', 0)}**;",
        f"- прочих repository paths: **{counts.get('other', 0)}**;",
        f"- repository-модулей с production consumers: **{data['repository_modules_with_production_consumers']}**;",
        f"- repository-модулей с package exports: **{data['repository_modules_with_package_exports']}**;",
        f"- repository-модулей без runtime consumers: **{data['repository_modules_without_runtime_consumers']}**;",
        f"- repository-модулей без любых references: **{data['repository_modules_without_references']}**;",
        f"- корневых Python-модулей: **{data['root_module_count']}**.",
        "",
        "## Категории корневых модулей",
        "",
    ]
    lines.extend(
        f"- {name}: **{count}**;" for name, count in categories.items()
    )
    lines.extend(
        [
            "",
            "## Кандидаты для первых P3E-срезов",
            "",
            "| Module | Layout | Production | Tests | Package exports | References |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for item in data["candidate_modules"]:
        lines.append(
            "| `{module}` | {layout} | {production} | {tests} | {exports} | {references} |".format(
                module=item["module"],
                layout=item["layout"],
                production=item["production_consumer_count"],
                tests=item["test_consumer_count"],
                exports=item["package_export_count"],
                references=item["reference_count"],
            )
        )
    lines.extend(["", "## Repository modules", ""])
    for layout in ("domain", "central", "root", "infrastructure", "other"):
        selected = [item for item in data["modules"] if item["layout"] == layout]
        if not selected:
            continue
        lines.extend([f"### {layout}", ""])
        for item in selected:
            domain = f" · domain `{item['domain']}`" if item["domain"] else ""
            lines.append(
                f"- `{item['module']}`{domain}: production {item['production_consumer_count']}, "
                f"tests {item['test_consumer_count']}, exports {item['package_export_count']}, "
                f"refs {item['reference_count']}."
            )
        lines.append("")
    next_slice = data["next_slice"]
    lines.extend(
        [
            "## Следующий срез",
            "",
            f"- фаза: **{next_slice['phase']}**;",
            f"- цель: **{next_slice['target']}**;",
            f"- первый кандидат: `{next_slice['candidate']}`;",
            f"- стратегия: {next_slice['strategy']}.",
            "",
            "## Правило обновления",
            "",
            "```bash",
            "python scripts/inventory_repository_layout.py --write --label <phase>",
            "python scripts/inventory_repository_layout.py --check --label <phase>",
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
        raise SystemExit("repository_layout_inventory.json устарел")
    if not MARKDOWN_PATH.is_file() or MARKDOWN_PATH.read_text(encoding="utf-8") != expected_markdown:
        raise SystemExit("repository_layout_inventory.md устарел")


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
