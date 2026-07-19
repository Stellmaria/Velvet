from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"
HANDLERS = PACKAGE / "handlers"
ROUTER_ROOT = PACKAGE / "presentation/telegram/router.py"
BUNDLE_DIR = PACKAGE / "presentation/telegram/routers"
COMPAT_PATH = PACKAGE / "presentation/telegram/compat.py"
JSON_PATH = ROOT / "docs/architecture_layout_inventory.json"
MARKDOWN_PATH = ROOT / "docs/architecture_layout_inventory.md"
MODULE_ALIAS_MARKER = "P3_COMPAT_MODULE_ALIAS"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _all_import_modules(path: Path) -> list[str]:
    return sorted(
        node.module
        for node in ast.walk(_tree(path))
        if isinstance(node, ast.ImportFrom) and node.module
    )


def _imports(path: Path, prefix: str) -> list[str]:
    return [name for name in _all_import_modules(path) if name.startswith(prefix)]


def _is_active_router_module(name: str) -> bool:
    return name.startswith("velvet_bot.handlers.") or name.startswith(
        "velvet_bot.presentation.telegram.routers."
    )


def _literal_assignment(path: Path, name: str) -> tuple[str, ...]:
    for node in _tree(path).body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            value = ast.literal_eval(node.value)
            return tuple(str(item) for item in value)
    raise RuntimeError(f"Не найдено literal assignment {name!r} в {path}")


def build_inventory(*, label: str = "working-tree") -> dict[str, Any]:
    root_handler_imports = _imports(ROUTER_ROOT, "velvet_bot.handlers.")
    bundle_files = sorted(
        path for path in BUNDLE_DIR.glob("*.py") if path.name != "__init__.py"
    )
    bundle_imports: list[str] = []
    bundle_rows: list[dict[str, Any]] = []
    for path in bundle_files:
        imports = [
            name for name in _all_import_modules(path) if _is_active_router_module(name)
        ]
        bundle_imports.extend(imports)
        bundle_rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "router_imports": imports,
                "router_count": len(imports),
            }
        )

    counts = Counter(bundle_imports)
    duplicate_imports = sorted(name for name, count in counts.items() if count > 1)
    handler_paths = sorted(
        path for path in HANDLERS.glob("*.py") if path.name != "__init__.py"
    )
    handler_facades = sorted(
        path
        for path in handler_paths
        if MODULE_ALIAS_MARKER in path.read_text(encoding="utf-8")
    )
    handler_implementations = sorted(set(handler_paths) - set(handler_facades))
    root_modules = sorted(
        path.relative_to(ROOT).as_posix()
        for path in PACKAGE.glob("*.py")
        if path.name != "__init__.py"
    )
    compatibility_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in PACKAGE.rglob("*.py")
        if "compat" in path.stem.casefold()
    )
    pre_components = _literal_assignment(COMPAT_PATH, "PRE_IMPORT_COMPONENTS")
    post_components = _literal_assignment(COMPAT_PATH, "POST_IMPORT_COMPONENTS")

    return {
        "schema_version": 2,
        "generated_from": label,
        "root_direct_handler_imports": root_handler_imports,
        "root_direct_handler_import_count": len(root_handler_imports),
        "router_bundles": bundle_rows,
        "active_bundle_router_imports": sorted(bundle_imports),
        "active_bundle_router_count": len(bundle_imports),
        "duplicate_bundle_router_imports": duplicate_imports,
        "duplicate_bundle_router_import_count": len(duplicate_imports),
        "legacy_handler_file_count": len(handler_paths),
        "legacy_handler_files": [
            path.relative_to(ROOT).as_posix() for path in handler_paths
        ],
        "legacy_handler_implementation_count": len(handler_implementations),
        "legacy_handler_implementations": [
            path.relative_to(ROOT).as_posix() for path in handler_implementations
        ],
        "handler_compatibility_facade_count": len(handler_facades),
        "handler_compatibility_facades": [
            path.relative_to(ROOT).as_posix() for path in handler_facades
        ],
        "root_level_module_count": len(root_modules),
        "root_level_modules": root_modules,
        "compatibility_file_count": len(compatibility_files),
        "compatibility_files": compatibility_files,
        "pre_import_compatibility_components": list(pre_components),
        "post_import_compatibility_components": list(post_components),
        "active_compatibility_component_count": len(pre_components) + len(post_components),
        "next_slice": {
            "phase": "P3C",
            "target": "characters and stories presentation controllers",
            "strategy": "canonical presentation modules plus temporary handler module aliases",
        },
    }


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Инвентаризация физической архитектуры Velvet",
        "",
        "Машинный срез переходной структуры после закрытия P2.",
        "",
        "## Сводка",
        "",
        f"- прямые imports `velvet_bot.handlers.*` в root Router: **{data['root_direct_handler_import_count']}**;",
        f"- доменных router bundles: **{len(data['router_bundles'])}**;",
        f"- активных router imports в bundles: **{data['active_bundle_router_count']}**;",
        f"- дублирующих регистраций между bundles: **{data['duplicate_bundle_router_import_count']}**;",
        f"- физических legacy handler-файлов: **{data['legacy_handler_file_count']}**;",
        f"- активных legacy handler implementations: **{data['legacy_handler_implementation_count']}**;",
        f"- временных handler module aliases: **{data['handler_compatibility_facade_count']}**;",
        f"- корневых Python-модулей `velvet_bot/*.py`: **{data['root_level_module_count']}**;",
        f"- файлов с `compat` в имени: **{data['compatibility_file_count']}**;",
        f"- активных compatibility-компонентов: **{data['active_compatibility_component_count']}**.",
        "",
        "## Router bundles",
        "",
    ]
    for item in data["router_bundles"]:
        lines.append(f"- `{item['path']}`: {item['router_count']} routers.")
    lines.extend(
        [
            "",
            "## Активная compatibility-граница",
            "",
            "### Pre-import",
            "",
        ]
    )
    lines.extend(
        f"- `{item}`." for item in data["pre_import_compatibility_components"]
    )
    lines.extend(["", "### Post-import", ""])
    lines.extend(
        f"- `{item}`." for item in data["post_import_compatibility_components"]
    )
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
            "После изменения root Router, bundles, `handlers/` или compatibility запустите:",
            "",
            "```bash",
            "python scripts/inventory_architecture_layout.py --write --label <phase>",
            "python scripts/inventory_architecture_layout.py --check --label <phase>",
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
        raise SystemExit("architecture_layout_inventory.json устарел")
    if not MARKDOWN_PATH.is_file() or MARKDOWN_PATH.read_text(encoding="utf-8") != expected_markdown:
        raise SystemExit("architecture_layout_inventory.md устарел")
    if data["root_direct_handler_import_count"] != 0:
        raise SystemExit("Root Router снова импортирует отдельные handlers")
    if data["duplicate_bundle_router_import_count"] != 0:
        raise SystemExit("Один router зарегистрирован в нескольких bundles")


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
