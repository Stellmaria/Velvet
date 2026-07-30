from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"

RootModuleCategory = Literal[
    "domain",
    "application",
    "infrastructure",
    "presentation",
    "worker",
    "public facade",
]

ALLOWED_CATEGORIES = {
    "domain",
    "application",
    "infrastructure",
    "presentation",
    "worker",
    "public facade",
}

# Any root-module addition/removal must deliberately update this baseline. The hash
# is calculated from sorted file names, so renames cannot quietly masquerade as an
# unchanged module count.
ROOT_MODULE_BASELINE_COUNT = 113
ROOT_MODULE_BASELINE_SHA256 = "pending-ci-baseline"

PUBLIC_FACADE_CONTRACTS: dict[str, str] = {
    "access.py": "Stable access-policy import surface backed by velvet_bot.core.access.",
    "config.py": "Stable settings import surface backed by velvet_bot.core.config.",
    "version.py": "Stable package version surface used by runtime and diagnostics.",
}

WORKER_EXACT = {
    "ai_job_runtime",
    "backup_runtime",
    "discussion_summary_runtime",
    "krita_supervisor",
    "local_ai_runtime",
    "publication_worker",
}

INFRASTRUCTURE_EXACT = {
    "database",
    "image_preview",
    "media_preview_persistence",
    "ollama_vision",
    "protected_bot",
    "runtime_log_hotfixes",
    "runtime_stability",
    "supervisor_client",
}

APPLICATION_EXACT = {
    "audit",
    "error_center",
    "owner_menu",
    "topics",
}

PRESENTATION_SUFFIXES = (
    "_callbacks",
    "_dashboard",
    "_preview",
    "_ui",
)

WORKER_SUFFIXES = (
    "_runtime",
    "_supervisor",
    "_worker",
)

INFRASTRUCTURE_SUFFIXES = (
    "_client",
    "_persistence",
)

APPLICATION_SUFFIXES = (
    "_actions",
    "_catalog",
    "_directory",
    "_ingest",
    "_management",
    "_operations",
    "_queries",
    "_relink",
    "_uploads",
    "_validation",
    "_workflow",
)

DOMAIN_PREFIXES = (
    "ai_",
    "alias_",
    "analytics_",
    "archive_",
    "calibrated_",
    "character_",
    "discussion_",
    "media",
    "multi_story_",
    "public_",
    "publication_",
    "quality_",
    "reference_",
    "resilient_",
    "set_",
    "story_",
    "telegram_",
    "velvet_",
    "visual_",
    "watermark_",
    "workspace_",
)


@dataclass(frozen=True, slots=True)
class RootModuleEntry:
    path: str
    module: str
    category: str
    classification_rule: str
    consumers: tuple[str, ...]
    side_effects: tuple[str, ...]
    public_contract: str | None


def _root_paths() -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in PACKAGE.glob("*.py")
            if path.name != "__init__.py"
        )
    )


def _baseline_hash(paths: tuple[Path, ...]) -> str:
    payload = "\n".join(path.name for path in paths).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _classify(path: Path) -> tuple[str, str]:
    name = path.name
    stem = path.stem
    if name in PUBLIC_FACADE_CONTRACTS:
        return "public facade", "explicit-public-contract"
    if stem in WORKER_EXACT or stem.endswith(WORKER_SUFFIXES):
        return "worker", "worker-runtime-name"
    if stem.endswith(PRESENTATION_SUFFIXES):
        return "presentation", "presentation-name"
    if stem in INFRASTRUCTURE_EXACT or stem.endswith(INFRASTRUCTURE_SUFFIXES):
        return "infrastructure", "infrastructure-name"
    if stem in APPLICATION_EXACT or stem.endswith(APPLICATION_SUFFIXES):
        return "application", "application-name"
    if stem.startswith(DOMAIN_PREFIXES):
        return "domain", "approved-domain-prefix"
    return "unclassified", "no-approved-root-contract"


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return type(node).__name__


def _is_main_guard(node: ast.If) -> bool:
    test = node.test
    return (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "__name__"
        and len(test.ops) == 1
        and isinstance(test.ops[0], ast.Eq)
        and len(test.comparators) == 1
        and isinstance(test.comparators[0], ast.Constant)
        and test.comparators[0].value == "__main__"
    )


def _is_type_checking_guard(node: ast.If) -> bool:
    return isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING"


def _side_effects(tree: ast.Module) -> tuple[str, ...]:
    effects: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            effects.add(f"top-level-call:{_dotted_name(node.value.func)}")
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if isinstance(value, ast.Call):
                effects.add(f"assignment-call:{_dotted_name(value.func)}")
            for target in targets:
                if isinstance(target, ast.Attribute):
                    effects.add(f"attribute-assignment:{_dotted_name(target)}")
        elif isinstance(node, ast.If):
            if not _is_main_guard(node) and not _is_type_checking_guard(node):
                effects.add("top-level-control-flow:if")
        elif isinstance(node, ast.Try):
            effects.add("top-level-control-flow:try")
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            effects.add(f"top-level-control-flow:{type(node).__name__.casefold()}")
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            effects.add(f"top-level-control-flow:{type(node).__name__.casefold()}")
    return tuple(sorted(effects))


def _imported_root_modules(tree: ast.Module) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if len(parts) == 2 and parts[0] == "velvet_bot":
                    imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            parts = module.split(".")
            if len(parts) == 2 and parts[0] == "velvet_bot":
                imported.add(module)
            elif module == "velvet_bot":
                for alias in node.names:
                    imported.add(f"velvet_bot.{alias.name}")
    return imported


def _consumer_index() -> dict[str, tuple[str, ...]]:
    consumers: defaultdict[str, set[str]] = defaultdict(set)
    for path in sorted(ROOT.rglob("*.py")):
        if any(part in {".git", ".venv", "venv", "__pycache__"} for part in path.parts):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError, UnicodeDecodeError):
            continue
        relative = path.relative_to(ROOT).as_posix()
        for module in _imported_root_modules(tree):
            consumers[module].add(relative)
    return {module: tuple(sorted(paths)) for module, paths in consumers.items()}


def build_inventory() -> dict[str, object]:
    paths = _root_paths()
    consumer_index = _consumer_index()
    entries: list[RootModuleEntry] = []
    for path in paths:
        module = f"velvet_bot.{path.stem}"
        category, rule = _classify(path)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        entries.append(
            RootModuleEntry(
                path=path.relative_to(ROOT).as_posix(),
                module=module,
                category=category,
                classification_rule=rule,
                consumers=consumer_index.get(module, ()),
                side_effects=_side_effects(tree),
                public_contract=PUBLIC_FACADE_CONTRACTS.get(path.name),
            )
        )
    category_counts = Counter(entry.category for entry in entries)
    return {
        "schema_version": 1,
        "root_module_count": len(entries),
        "root_module_name_sha256": _baseline_hash(paths),
        "unclassified_count": category_counts.get("unclassified", 0),
        "category_counts": dict(sorted(category_counts.items())),
        "entries": [asdict(entry) for entry in entries],
    }


def validate_inventory(data: dict[str, object]) -> list[str]:
    errors: list[str] = []
    count = int(data["root_module_count"])
    digest = str(data["root_module_name_sha256"])
    entries = list(data["entries"])
    if count != ROOT_MODULE_BASELINE_COUNT:
        errors.append(
            f"root module count changed: expected {ROOT_MODULE_BASELINE_COUNT}, got {count}"
        )
    if digest != ROOT_MODULE_BASELINE_SHA256:
        errors.append(
            "root module filename baseline changed: "
            f"expected {ROOT_MODULE_BASELINE_SHA256}, got {digest}"
        )
    unclassified = [entry["path"] for entry in entries if entry["category"] == "unclassified"]
    if unclassified:
        errors.append("unclassified root modules: " + ", ".join(unclassified))
    invalid = [entry["path"] for entry in entries if entry["category"] not in ALLOWED_CATEGORIES]
    if invalid:
        errors.append("invalid root module categories: " + ", ".join(invalid))
    for entry in entries:
        if entry["category"] == "public facade" and not entry["public_contract"]:
            errors.append(f"public facade lacks explicit contract: {entry['path']}")
    return errors


def _print_summary(data: dict[str, object]) -> None:
    print(f"Root modules: {data['root_module_count']}")
    print(f"Filename SHA256: {data['root_module_name_sha256']}")
    print(f"Unclassified: {data['unclassified_count']}")
    for category, count in dict(data["category_counts"]).items():
        print(f"- {category}: {count}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory velvet_bot root modules")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    data = build_inventory()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        _print_summary(data)
    if args.check:
        errors = validate_inventory(data)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
