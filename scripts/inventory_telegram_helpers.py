from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"
ROUTERS = "velvet_bot.presentation.telegram.routers"
SHARED_ROOT = PACKAGE / "presentation" / "telegram" / "shared"

DuplicateKind = Literal["real-duplicate", "generated/compat", "allowed-template"]

FAMILY_CONTRACTS: dict[str, tuple[str, ...]] = {
    "safe edit/send fallback": (
        "velvet_bot.presentation.telegram.shared.editing",
    ),
    "pagination keyboards": (
        "velvet_bot.presentation.telegram.shared.navigation",
    ),
    "deletion helpers": (
        "velvet_bot.presentation.telegram.shared.deletion",
    ),
    "media download/preview/original delivery": (
        "velvet_bot.image_preview",
        "velvet_bot.public_archive_display",
    ),
    "callback navigation and back buttons": (
        "velvet_bot.presentation.telegram.shared.navigation",
    ),
    "owner/editor/member guards": (
        "velvet_bot.core.access",
        "velvet_bot.presentation.telegram.runtime_contracts",
    ),
    "worker compensation/reporting boilerplate": (
        "velvet_bot.domains.media_generation.worker",
        "velvet_bot.domains.media_generation.friendly_worker",
    ),
    "message chunking/HTML fallback": (
        "velvet_bot.presentation.telegram.shared.text",
    ),
    "repeated progress-card updates": (
        "velvet_bot.app.telegram_progress_resilience",
    ),
}

FAMILY_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "safe edit/send fallback",
        ("safe_edit", "edit_text", "edit_message", "send_fallback", "not_modified"),
    ),
    (
        "pagination keyboards",
        ("pagination", "paginate", "page_keyboard", "pager", "previous_page", "next_page"),
    ),
    (
        "deletion helpers",
        ("delete_message", "safe_delete", "deletion", "remove_message", "purge_message"),
    ),
    (
        "media download/preview/original delivery",
        ("download", "preview", "original", "deliver_media", "media_file", "input_media"),
    ),
    (
        "callback navigation and back buttons",
        ("back_keyboard", "navigation", "callback_back", "home_button", "menu_keyboard"),
    ),
    (
        "owner/editor/member guards",
        ("owner_guard", "editor_guard", "member_guard", "require_owner", "require_editor", "access_guard"),
    ),
    (
        "worker compensation/reporting boilerplate",
        ("compens", "worker_report", "report_failure", "settle", "rollback_worker", "retry_report"),
    ),
    (
        "message chunking/HTML fallback",
        ("chunk", "split_message", "long_message", "html_fallback", "parse_mode_fallback"),
    ),
    (
        "repeated progress-card updates",
        ("progress", "update_card", "status_card", "publish_progress"),
    ),
)

PRIVATE_HELPER_MARKERS = tuple(
    marker
    for _family, markers in FAMILY_MARKERS
    for marker in markers
)

FORBIDDEN_SHARED_IMPORT_PREFIXES = (
    "velvet_bot.database",
    "velvet_bot.domains",
    "velvet_bot.repositories",
)
SQL_PATTERN = re.compile(
    r"(?:\bSELECT\b.+\bFROM\b|\bINSERT\s+INTO\b|\bUPDATE\b.+\bSET\b|\bDELETE\s+FROM\b)",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True, slots=True)
class FunctionOccurrence:
    path: str
    module: str
    name: str
    line: int
    end_line: int


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    digest: str
    kind: DuplicateKind
    family: str
    occurrences: tuple[FunctionOccurrence, ...]


@dataclass(frozen=True, slots=True)
class PrivateHelperImport:
    path: str
    line: int
    source_module: str
    imported_name: str


def _python_paths() -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(PACKAGE.rglob("*.py"))
        if "__pycache__" not in path.parts
    )


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def _module_path(module: str) -> Path:
    return ROOT.joinpath(*module.split(".")).with_suffix(".py")


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _function_fingerprint(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    body = _strip_docstring(list(node.body))
    if not body:
        return None
    node_count = sum(1 for statement in body for _ in ast.walk(statement))
    line_span = max(1, int(getattr(node, "end_lineno", node.lineno)) - node.lineno + 1)
    if node_count < 12 or line_span < 4:
        return None
    payload = {
        "async": isinstance(node, ast.AsyncFunctionDef),
        "positional": len(node.args.posonlyargs) + len(node.args.args),
        "kwonly": len(node.args.kwonlyargs),
        "vararg": node.args.vararg is not None,
        "kwarg": node.args.kwarg is not None,
        "body": [ast.dump(statement, include_attributes=False) for statement in body],
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _family_for(occurrences: tuple[FunctionOccurrence, ...]) -> str:
    haystack = " ".join(
        f"{item.path} {item.name}".casefold().replace("-", "_")
        for item in occurrences
    )
    for family, markers in FAMILY_MARKERS:
        if any(marker in haystack for marker in markers):
            return family
    return "other repeated implementation"


def _kind_for(occurrences: tuple[FunctionOccurrence, ...], family: str) -> DuplicateKind:
    lowered = " ".join(item.path.casefold() for item in occurrences)
    if any(marker in lowered for marker in ("generated", "compat", "legacy", "migration")):
        return "generated/compat"
    if family in FAMILY_CONTRACTS:
        return "real-duplicate"
    return "allowed-template"


def _duplicate_groups(paths: tuple[Path, ...]) -> tuple[DuplicateGroup, ...]:
    by_digest: defaultdict[str, list[FunctionOccurrence]] = defaultdict(list)
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        module = _module_name(path)
        relative = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            digest = _function_fingerprint(node)
            if digest is None:
                continue
            by_digest[digest].append(
                FunctionOccurrence(
                    path=relative,
                    module=module,
                    name=node.name,
                    line=node.lineno,
                    end_line=int(getattr(node, "end_lineno", node.lineno)),
                )
            )

    groups: list[DuplicateGroup] = []
    for digest, raw_occurrences in sorted(by_digest.items()):
        if len(raw_occurrences) < 2:
            continue
        occurrences = tuple(sorted(raw_occurrences, key=lambda item: (item.path, item.line)))
        family = _family_for(occurrences)
        groups.append(
            DuplicateGroup(
                digest=digest,
                kind=_kind_for(occurrences, family),
                family=family,
                occurrences=occurrences,
            )
        )
    return tuple(groups)


def _resolve_import(current_module: str, node: ast.ImportFrom) -> str:
    module = node.module or ""
    if node.level == 0:
        return module
    package = current_module.split(".")[:-1]
    keep = max(0, len(package) - node.level + 1)
    prefix = package[:keep]
    suffix = module.split(".") if module else []
    return ".".join((*prefix, *suffix))


def _looks_like_helper(name: str) -> bool:
    normalized = name.casefold().replace("-", "_")
    return name.startswith("_") and any(
        marker in normalized for marker in PRIVATE_HELPER_MARKERS
    )


def _private_helper_imports(paths: tuple[Path, ...]) -> tuple[PrivateHelperImport, ...]:
    imports: list[PrivateHelperImport] = []
    for path in paths:
        current_module = _module_name(path)
        if not current_module.startswith(ROUTERS):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            source_module = _resolve_import(current_module, node)
            if not source_module.startswith(ROUTERS) or source_module == current_module:
                continue
            for alias in node.names:
                if _looks_like_helper(alias.name):
                    imports.append(
                        PrivateHelperImport(
                            path=path.relative_to(ROOT).as_posix(),
                            line=node.lineno,
                            source_module=source_module,
                            imported_name=alias.name,
                        )
                    )
    return tuple(sorted(imports, key=lambda item: (item.path, item.line, item.imported_name)))


def _shared_contract_violations() -> tuple[str, ...]:
    violations: list[str] = []
    for path in sorted(SHARED_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        relative = path.relative_to(ROOT).as_posix()
        for node in ast.walk(tree):
            imported: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                imported = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported = (node.module or "",)
            for module in imported:
                if module.startswith(FORBIDDEN_SHARED_IMPORT_PREFIXES):
                    violations.append(f"{relative}:{node.lineno}: forbidden import {module}")
        if SQL_PATTERN.search(source):
            violations.append(f"{relative}: SQL/business query text is forbidden")
    return tuple(violations)


def _missing_contract_modules() -> tuple[str, ...]:
    missing: list[str] = []
    for family, modules in FAMILY_CONTRACTS.items():
        for module in modules:
            path = _module_path(module)
            package_init = ROOT.joinpath(*module.split("."), "__init__.py")
            if not path.exists() and not package_init.exists():
                missing.append(f"{family}: {module}")
    return tuple(missing)


def build_inventory() -> dict[str, object]:
    paths = _python_paths()
    duplicate_groups = _duplicate_groups(paths)
    private_imports = _private_helper_imports(paths)
    family_counts = Counter(group.family for group in duplicate_groups)
    kind_counts = Counter(group.kind for group in duplicate_groups)
    return {
        "schema_version": 1,
        "production_python_files": len(paths),
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_kind_counts": dict(sorted(kind_counts.items())),
        "duplicate_family_counts": {
            family: family_counts.get(family, 0)
            for family in (*FAMILY_CONTRACTS, "other repeated implementation")
        },
        "family_contracts": {
            family: list(modules) for family, modules in FAMILY_CONTRACTS.items()
        },
        "duplicate_groups": [
            {
                "digest": group.digest,
                "kind": group.kind,
                "family": group.family,
                "occurrences": [asdict(item) for item in group.occurrences],
            }
            for group in duplicate_groups
        ],
        "private_helper_import_count": len(private_imports),
        "private_helper_imports": [asdict(item) for item in private_imports],
        "shared_contract_violations": list(_shared_contract_violations()),
        "missing_contract_modules": list(_missing_contract_modules()),
    }


def validate_inventory(data: dict[str, object]) -> list[str]:
    errors: list[str] = []
    private_imports = list(data["private_helper_imports"])
    if private_imports:
        rendered = ", ".join(
            f"{item['path']}:{item['line']} -> {item['source_module']}.{item['imported_name']}"
            for item in private_imports
        )
        errors.append("cross-controller private helper imports: " + rendered)
    violations = list(data["shared_contract_violations"])
    if violations:
        errors.append("shared helper boundary violations: " + "; ".join(violations))
    missing = list(data["missing_contract_modules"])
    if missing:
        errors.append("missing helper contract modules: " + ", ".join(missing))
    groups = list(data["duplicate_groups"])
    invalid = [
        group["digest"]
        for group in groups
        if group["kind"] not in {"real-duplicate", "generated/compat", "allowed-template"}
    ]
    if invalid:
        errors.append("unclassified duplicate groups: " + ", ".join(invalid))
    return errors


def _print_summary(data: dict[str, object]) -> None:
    print(f"Production Python files: {data['production_python_files']}")
    print(f"Duplicate groups: {data['duplicate_group_count']}")
    print(f"Private helper imports: {data['private_helper_import_count']}")
    for kind, count in dict(data["duplicate_kind_counts"]).items():
        print(f"- {kind}: {count}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory shared Telegram helper debt")
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
