from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"
DOCS = ROOT / "docs"
INVENTORY_JSON = DOCS / "package_architecture_inventory.json"
INVENTORY_MD = DOCS / "package_architecture_inventory.md"
EXEMPTIONS_JSON = DOCS / "package_architecture_exemptions.json"
SHARED_JSON = DOCS / "shared_contract_inventory.json"
ARCHITECTURE_JSON = DOCS / "architecture_layout_inventory.json"
REPOSITORY_JSON = DOCS / "repository_layout_inventory.json"
ROOT_INVENTORY_SCRIPT = ROOT / "scripts" / "inventory_root_modules.py"

SQL_PATTERN = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+TABLE|ALTER\s+TABLE|"
    r"DROP\s+TABLE|WITH\s+[A-Za-z_])\b",
    re.IGNORECASE,
)
INSTALL_FILE_SUFFIXES = ("_install.py", "_hotfix.py", "_fix.py")
LAYER_PREFIXES = {
    "app": "composition",
    "application": "application",
    "core": "core",
    "domains": "domain",
    "infrastructure": "infrastructure",
    "presentation": "presentation",
    "services": "service",
    "workers": "worker",
}
REQUIRED_EXCEPTION_FIELDS = {
    "id",
    "owner",
    "reason",
    "consumers",
    "replacement",
    "removal_condition",
    "regression_test",
    "issue",
}
MONOLITH_LOC_LIMIT = 800
MONOLITH_FUNCTION_LIMIT = 180


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(rows: list[str]) -> str:
    return hashlib.sha256("\n".join(sorted(rows)).encode("utf-8")).hexdigest()


def _production_paths() -> tuple[Path, ...]:
    return tuple(
        sorted(
            path
            for path in PACKAGE.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    )


def _module_name(path: Path) -> str:
    parts = list(path.relative_to(ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _layer(path: Path) -> str:
    parts = path.relative_to(PACKAGE).parts
    if len(parts) == 1:
        return "root"
    return LAYER_PREFIXES.get(parts[0], "other")


def _target_package(path: Path, root_targets: dict[str, str]) -> str:
    layer = _layer(path)
    if layer != "root":
        return layer
    category = root_targets.get(_module_name(path), "unclassified")
    return {
        "domain": "domains/<bounded-domain>",
        "application": "application/<bounded-use-case>",
        "infrastructure": "infrastructure/<adapter>",
        "presentation": "presentation/telegram/<surface>",
        "worker": "workers/<runtime>",
        "public facade": "root public facade",
    }.get(category, "#463 classification required")


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _dotted(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, (ast.Call, ast.Subscript)):
        return _dotted(node.func if isinstance(node, ast.Call) else node.value)
    return ""


def _resolve_import(
    current_module: str,
    level: int,
    module: str | None,
    *,
    is_package: bool,
) -> str:
    if level <= 0:
        return module or ""
    package_parts = current_module.split(".") if is_package else current_module.split(".")[:-1]
    prefix = package_parts[: max(0, len(package_parts) - (level - 1))]
    if module:
        prefix.extend(module.split("."))
    return ".".join(prefix)


def _imports(
    tree: ast.Module,
    module_name: str,
    *,
    is_package: bool,
) -> tuple[dict[str, str], list[str]]:
    aliases: dict[str, str] = {}
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                aliases[local] = alias.name
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            source = _resolve_import(
                module_name,
                node.level,
                node.module,
                is_package=is_package,
            )
            if source:
                modules.add(source)
            for alias in node.names:
                if alias.name == "*":
                    continue
                aliases[alias.asname or alias.name] = (
                    f"{source}.{alias.name}" if source else alias.name
                )
    return aliases, sorted(modules)


def _owner(tree: ast.Module, line: int) -> str:
    owner = "<module>"
    span = 10**9
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = int(node.lineno)
        end = int(getattr(node, "end_lineno", start) or start)
        if start <= line <= end and end - start < span:
            owner = node.name
            span = end - start
    return owner


def _violation(
    category: str,
    path: str,
    rows: list[str],
    *,
    summary: str,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    fingerprint = _sha(rows)
    short = fingerprint[:16]
    return {
        "id": f"{category}:{path}:{short}",
        "category": category,
        "path": path,
        "fingerprint": fingerprint,
        "summary": summary,
        "details": details or {},
    }


def _persistence_path(path: Path) -> bool:
    stem = path.stem.casefold()
    parts = {part.casefold() for part in path.parts}
    return (
        any(
            token in stem
            for token in (
                "repository",
                "queries",
                "query",
                "store",
                "database",
                "persistence",
            )
        )
        or "repositories" in parts
        or "migrations" in parts
    )


def _scan_module(path: Path, root_targets: dict[str, str]) -> dict[str, Any]:
    relative = path.relative_to(ROOT).as_posix()
    module_name = _module_name(path)
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=relative)
    aliases, imports = _imports(
        tree,
        module_name,
        is_package=path.name == "__init__.py",
    )
    internal_imports = sorted(value for value in imports if value.startswith("velvet_bot"))
    external_import_count = len(imports) - len(internal_imports)
    functions = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    handlers = [
        node
        for node in functions
        if any(
            any(
                token in _dotted(decorator)
                for token in (".message", ".callback_query", ".inline_query")
            )
            for decorator in node.decorator_list
        )
    ]
    max_function_length = max(
        (
            int(getattr(node, "end_lineno", node.lineno) or node.lineno)
            - int(node.lineno)
            + 1
            for node in functions
        ),
        default=0,
    )
    branch_count = sum(
        isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match))
        for node in ast.walk(tree)
    )

    sql_rows: list[str] = []
    sql_keywords: set[str] = set()
    sql_owners: set[str] = set()
    acquire_rows: list[str] = []
    acquire_calls: set[str] = set()
    acquire_owners: set[str] = set()
    foreign_rows: list[str] = []
    foreign_targets: set[str] = set()
    dynamic_rows: list[str] = []
    dynamic_calls: set[str] = set()
    env_rows: list[dict[str, Any]] = []
    polling_rows: list[dict[str, Any]] = []
    worker_registrations: list[dict[str, Any]] = []
    install_definitions: set[str] = set()
    install_calls: list[dict[str, Any]] = []
    any_count = 0
    cast_count = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "Any":
            any_count += 1
        if isinstance(node, ast.Call):
            call = _dotted(node.func)
            owner = _owner(tree, node.lineno)
            if call in {"cast", "typing.cast"} or call.endswith(".cast"):
                cast_count += 1
            if call in {"importlib.import_module", "__import__"}:
                dynamic_calls.add(call)
                dynamic_rows.append(f"{owner}|{call}|{ast.dump(node, include_attributes=False)}")
            if call.endswith(".acquire"):
                acquire_calls.add(call)
                acquire_owners.add(owner)
                acquire_rows.append(f"{owner}|{call}|{ast.dump(node, include_attributes=False)}")
            if call in {"os.getenv", "os.environ.get", "environ.get"} or call.endswith(".getenv"):
                env_rows.append({"line": node.lineno, "owner": owner, "call": call})
            if call.endswith("sleep") or "poll" in call.casefold():
                values = [
                    value.value
                    for value in ast.walk(node)
                    if isinstance(value, ast.Constant)
                    and isinstance(value.value, (int, float))
                ]
                if values:
                    polling_rows.append(
                        {"line": node.lineno, "owner": owner, "call": call, "values": values}
                    )
            if call.split(".")[-1].startswith("install_"):
                install_calls.append({"line": node.lineno, "call": call})
            if "worker" in call.casefold() and any(
                token in call.casefold() for token in ("register", "add", "create", "worker")
            ):
                worker_registrations.append(
                    {"line": node.lineno, "owner": owner, "call": call}
                )
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("install_"):
            install_definitions.add(node.name)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            match = SQL_PATTERN.search(node.value)
            if match:
                normalized = " ".join(node.value.split())
                owner = _owner(tree, node.lineno)
                keyword = match.group(1).upper()
                sql_keywords.add(keyword)
                sql_owners.add(owner)
                sql_rows.append(f"{owner}|{keyword}|{normalized}")
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = list(node.targets) if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, ast.Attribute):
                    continue
                target_name = _dotted(target)
                root_name = target_name.split(".", 1)[0]
                if root_name not in aliases:
                    continue
                owner = _owner(tree, target.lineno)
                origin = aliases[root_name]
                foreign_targets.add(target_name)
                foreign_rows.append(f"{owner}|{origin}|{target_name}")

    layer = _layer(path)
    aiogram_imports = sorted(
        value for value in imports if value == "aiogram" or value.startswith("aiogram.")
    )
    type_ignore_rows = [
        f"{index}:{line.strip()}"
        for index, line in enumerate(lines, start=1)
        if "# type: ignore" in line
    ]
    method_assign_rows = [row for row in type_ignore_rows if "method-assign" in row]
    installed_rows = [
        f"{index}:{line.strip()}"
        for index, line in enumerate(lines, start=1)
        if "_INSTALLED" in line
    ]
    package_getattr = any(node.name == "__getattr__" for node in functions)
    violations: list[dict[str, Any]] = []

    if layer in {"domain", "service"} and aiogram_imports:
        violations.append(
            _violation(
                "domain-aiogram-import",
                relative,
                aiogram_imports,
                summary=f"{len(aiogram_imports)} aiogram imports in {layer}",
                details={"imports": aiogram_imports},
            )
        )
    forbidden = sorted(
        value
        for value in internal_imports
        if layer == "domain"
        and value.startswith(("velvet_bot.presentation", "velvet_bot.app"))
    )
    if forbidden:
        violations.append(
            _violation(
                "domain-layer-import",
                relative,
                forbidden,
                summary=f"{len(forbidden)} domain imports from app/presentation",
                details={"imports": forbidden},
            )
        )
    if sql_rows and not _persistence_path(path):
        violations.append(
            _violation(
                "sql-outside-persistence",
                relative,
                sql_rows,
                summary=f"{len(sql_rows)} SQL literals outside persistence",
                details={
                    "count": len(sql_rows),
                    "keywords": sorted(sql_keywords),
                    "owners": sorted(sql_owners),
                },
            )
        )
    if acquire_rows and not _persistence_path(path):
        violations.append(
            _violation(
                "database-acquire-outside-persistence",
                relative,
                acquire_rows,
                summary=f"{len(acquire_rows)} acquire calls outside persistence",
                details={
                    "count": len(acquire_rows),
                    "calls": sorted(acquire_calls),
                    "owners": sorted(acquire_owners),
                },
            )
        )
    if foreign_rows:
        violations.append(
            _violation(
                "foreign-assignment",
                relative,
                foreign_rows,
                summary=f"{len(foreign_rows)} assignments to imported owners",
                details={"count": len(foreign_rows), "targets": sorted(foreign_targets)},
            )
        )
    if dynamic_rows:
        violations.append(
            _violation(
                "dynamic-import",
                relative,
                dynamic_rows,
                summary=f"{len(dynamic_rows)} dynamic imports",
                details={"count": len(dynamic_rows), "calls": sorted(dynamic_calls)},
            )
        )
    if path.name.endswith(INSTALL_FILE_SUFFIXES):
        violations.append(
            _violation(
                "installer-like-module",
                relative,
                [path.name],
                summary="installer/hotfix/fix module requires explicit retirement",
            )
        )
    if method_assign_rows:
        violations.append(
            _violation(
                "method-assign-ignore",
                relative,
                method_assign_rows,
                summary=f"{len(method_assign_rows)} method-assign ignores",
                details={"count": len(method_assign_rows)},
            )
        )
    if type_ignore_rows:
        violations.append(
            _violation(
                "type-ignore-usage",
                relative,
                type_ignore_rows,
                summary=f"{len(type_ignore_rows)} type-ignore comments",
                details={"count": len(type_ignore_rows)},
            )
        )
    if any_count:
        violations.append(
            _violation(
                "typing-any-usage",
                relative,
                [f"Any-count={any_count}"],
                summary=f"{any_count} Any references",
                details={"count": any_count},
            )
        )
    if package_getattr:
        violations.append(
            _violation(
                "package-getattr-side-effect",
                relative,
                ["__getattr__"],
                summary="package __getattr__ may trigger runtime composition",
            )
        )
    if installed_rows:
        violations.append(
            _violation(
                "installed-sentinel",
                relative,
                installed_rows,
                summary=f"{len(installed_rows)} _INSTALLED references",
                details={"count": len(installed_rows)},
            )
        )
    if len(lines) > MONOLITH_LOC_LIMIT:
        violations.append(
            _violation(
                "monolithic-module-loc",
                relative,
                [f"loc={len(lines)}"],
                summary=f"{len(lines)} LOC exceeds {MONOLITH_LOC_LIMIT}",
                details={"loc": len(lines), "limit": MONOLITH_LOC_LIMIT},
            )
        )
    if max_function_length > MONOLITH_FUNCTION_LIMIT:
        violations.append(
            _violation(
                "monolithic-function",
                relative,
                [f"max-function-lines={max_function_length}"],
                summary=(
                    f"max function {max_function_length} lines exceeds "
                    f"{MONOLITH_FUNCTION_LIMIT}"
                ),
                details={
                    "max_function_length": max_function_length,
                    "limit": MONOLITH_FUNCTION_LIMIT,
                },
            )
        )

    return {
        "path": relative,
        "module": module_name,
        "layer": layer,
        "target_package": _target_package(path, root_targets),
        "loc": len(lines),
        "function_count": len(functions),
        "class_count": len(classes),
        "handler_count": len(handlers),
        "max_function_length": max_function_length,
        "branch_count": branch_count,
        "internal_imports": internal_imports,
        "external_import_count": external_import_count,
        "aiogram_imports": aiogram_imports,
        "sql_literal_count": len(sql_rows),
        "database_acquire_count": len(acquire_rows),
        "foreign_assignment_targets": sorted(foreign_targets),
        "dynamic_import_count": len(dynamic_rows),
        "any_count": any_count,
        "cast_count": cast_count,
        "type_ignore_count": len(type_ignore_rows),
        "method_assign_ignore_count": len(method_assign_rows),
        "install_definitions": sorted(install_definitions),
        "install_calls": install_calls,
        "installed_sentinel_count": len(installed_rows),
        "package_getattr": package_getattr,
        "env_reads": env_rows,
        "polling_values": polling_rows,
        "worker_registrations": worker_registrations,
        "violations": violations,
    }


def _load_root_targets() -> tuple[dict[str, str], dict[str, Any]]:
    module_name = "_velvet_inventory_root_modules"
    spec = importlib.util.spec_from_file_location(module_name, ROOT_INVENTORY_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load root module inventory")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        data = module.build_inventory()
    finally:
        sys.modules.pop(module_name, None)
    return (
        {str(row["module"]): str(row["category"]) for row in data["entries"]},
        data,
    )


def _reverse_consumers(modules: list[dict[str, Any]]) -> dict[str, list[str]]:
    result: defaultdict[str, set[str]] = defaultdict(set)
    for row in modules:
        for imported in row["internal_imports"]:
            result[str(imported)].add(str(row["path"]))
    return {module: sorted(paths) for module, paths in result.items()}


def _installer_graph(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_module = {str(row["module"]): row for row in modules}
    app_init = by_module.get("velvet_bot.app")
    if app_init is None:
        return []
    path = ROOT / str(app_init["path"])
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases, _ = _imports(tree, "velvet_bot.app", is_package=True)
    graph: list[dict[str, Any]] = []
    for call in sorted(app_init["install_calls"], key=lambda row: int(row["line"])):
        local = str(call["call"]).split(".")[0]
        origin = aliases.get(local, local)
        owner_module = origin.rsplit(".", 1)[0] if "." in origin else origin
        owner_row = by_module.get(owner_module, {})
        graph.append(
            {
                "order": len(graph) + 1,
                "line": int(call["line"]),
                "call": str(call["call"]),
                "origin": origin,
                "owner_module": owner_module,
                "patched_symbols": list(owner_row.get("foreign_assignment_targets", [])),
            }
        )
    return graph


def _shared_fingerprint(shared: dict[str, Any]) -> str:
    rows = [
        "|".join(
            (
                str(item.get("path", "")),
                str(item.get("line", "")),
                str(item.get("symbol", "")),
                str(item.get("access_kind", item.get("kind", ""))),
            )
        )
        for item in shared.get("private_contract_accesses", [])
    ]
    return _sha(rows)


def _suggest_exception(
    violation: dict[str, Any],
    consumers: dict[str, list[str]],
) -> dict[str, Any]:
    path = str(violation["path"])
    category = str(violation["category"])
    lowered = path.casefold()
    if "media_generation" in lowered or "delivery" in lowered or "grs" in lowered:
        issue = "#457" if "delivery" in lowered or "worker" in lowered else "#459"
    elif "auf" in lowered and category in {
        "sql-outside-persistence",
        "monolithic-module-loc",
        "monolithic-function",
    }:
        issue = "#458"
    elif path.startswith("velvet_bot/app/") or category in {
        "foreign-assignment",
        "installer-like-module",
        "installed-sentinel",
        "package-getattr-side-effect",
        "method-assign-ignore",
    }:
        issue = "#455"
    elif path.count("/") == 1:
        issue = "#463"
    else:
        issue = "#460"
    owners = {
        "#455": "application-composition",
        "#457": "media-delivery",
        "#458": "auf-application-presentation",
        "#459": "provider-adapters",
        "#460": "architecture-governance",
        "#463": "root-module-migration",
    }
    module = path.removesuffix("/__init__.py").removesuffix(".py").replace("/", ".")
    consumer_rows = consumers.get(module, []) or [path]
    return {
        "id": str(violation["id"]),
        "owner": owners[issue],
        "reason": f"Existing {category} debt captured by the reviewed baseline.",
        "consumers": consumer_rows,
        "replacement": f"Canonical boundary tracked by {issue}.",
        "removal_condition": (
            f"Remove this exemption when {issue} retires the fingerprinted debt "
            "without behavior regression."
        ),
        "regression_test": "tests/test_package_architecture_inventory.py",
        "issue": issue,
    }


def build_inventory(*, label: str = "working-tree") -> dict[str, Any]:
    root_targets, root_inventory = _load_root_targets()
    modules = [_scan_module(path, root_targets) for path in _production_paths()]
    violations = [item for row in modules for item in row["violations"]]
    architecture = _json(ARCHITECTURE_JSON)
    repositories = _json(REPOSITORY_JSON)
    shared = _json(SHARED_JSON)
    components = list(architecture.get("pre_import_compatibility_components", [])) + list(
        architecture.get("post_import_compatibility_components", [])
    )
    compatibility = [
        {
            "component": component,
            "owner": "runtime-compatibility",
            "replacement": "Explicit composition registration or removal regression.",
            "expiry": "Retire after consumers migrate under #420/#455.",
            "issue": "#420",
        }
        for component in components
    ]
    return {
        "schema_version": 1,
        "generated_from": label,
        "production_module_count": len(modules),
        "production_loc": sum(int(row["loc"]) for row in modules),
        "layer_counts": dict(sorted(Counter(str(row["layer"]) for row in modules).items())),
        "root_module_count": int(root_inventory["root_module_count"]),
        "root_module_sha256": str(root_inventory["root_module_name_sha256"]),
        "root_unclassified_count": int(root_inventory["unclassified_count"]),
        "router_count": int(architecture["active_bundle_router_count"]),
        "router_duplicate_count": int(architecture["duplicate_bundle_router_import_count"]),
        "repository_module_count": int(repositories["repository_module_count"]),
        "runtime_compatibility_components": compatibility,
        "shared_contract_summary": {
            "production_python_files": int(shared["production_python_files"]),
            "function_count": int(shared["function_count"]),
            "private_contract_access_count": int(shared["private_contract_access_count"]),
            "blocking_private_contract_access_count": int(
                shared["blocking_private_contract_access_count"]
            ),
            "exact_duplicate_group_count": int(shared["exact_duplicate_group_count"]),
            "normalized_duplicate_group_count": int(
                shared["normalized_duplicate_group_count"]
            ),
            "semantic_near_duplicate_group_count": int(
                shared["semantic_near_duplicate_group_count"]
            ),
            "private_access_sha256": _shared_fingerprint(shared),
        },
        "installer_graph": _installer_graph(modules),
        "violation_count": len(violations),
        "violation_counts": dict(
            sorted(Counter(str(item["category"]) for item in violations).items())
        ),
        "violations": sorted(violations, key=lambda row: str(row["id"])),
        "modules": modules,
    }


def build_exemptions(data: dict[str, Any], *, label: str) -> dict[str, Any]:
    consumers = _reverse_consumers(list(data["modules"]))
    exceptions = [
        _suggest_exception(violation, consumers)
        for violation in data["violations"]
    ]
    return {
        "schema_version": 1,
        "generated_from": label,
        "baseline_issue": "#460",
        "shared_private_access_sha256": data["shared_contract_summary"][
            "private_access_sha256"
        ],
        "root_module_sha256": data["root_module_sha256"],
        "exceptions": sorted(exceptions, key=lambda row: str(row["id"])),
    }


def render_markdown(data: dict[str, Any], exemptions: dict[str, Any]) -> str:
    shared = data["shared_contract_summary"]
    lines = [
        "# Package-wide architecture inventory",
        "",
        f"- Generated from: `{data['generated_from']}`",
        f"- Production modules: **{data['production_module_count']}**",
        f"- Production LOC: **{data['production_loc']}**",
        f"- Root modules: **{data['root_module_count']}**",
        f"- Active Router imports: **{data['router_count']}**",
        f"- Repository modules: **{data['repository_module_count']}**",
        f"- Startup installer stages: **{len(data['installer_graph'])}**",
        f"- Registered package violations: **{data['violation_count']}**",
        f"- Registered exemptions: **{len(exemptions['exceptions'])}**",
        "",
        "## Layers",
        "",
    ]
    lines.extend(
        f"- `{layer}`: **{count}** modules"
        for layer, count in data["layer_counts"].items()
    )
    lines.extend(
        [
            "",
            "## Shared/private baseline",
            "",
            f"- private cross-module accesses: **{shared['private_contract_access_count']}**",
            f"- blocking known private contracts: **{shared['blocking_private_contract_access_count']}**",
            f"- exact / normalized / semantic duplicate groups: **{shared['exact_duplicate_group_count']} / {shared['normalized_duplicate_group_count']} / {shared['semantic_near_duplicate_group_count']}**",
            f"- private access fingerprint: `{shared['private_access_sha256']}`",
            "",
            "## Installer graph",
            "",
        ]
    )
    for item in data["installer_graph"]:
        patched = ", ".join(f"`{value}`" for value in item["patched_symbols"]) or "none detected"
        lines.append(
            f"{item['order']}. `{item['call']}` from `{item['origin']}`; patched symbols: {patched}."
        )
    lines.extend(["", "## Violation baseline", ""])
    lines.extend(
        f"- `{category}`: **{count}**"
        for category, count in data["violation_counts"].items()
    )
    lines.extend(["", "## Largest modules", ""])
    largest = sorted(data["modules"], key=lambda row: int(row["loc"]), reverse=True)[:20]
    for item in largest:
        lines.append(
            f"- `{item['path']}`: {item['loc']} LOC, {item['function_count']} functions, "
            f"max function {item['max_function_length']} lines, target `{item['target_package']}`."
        )
    lines.extend(["", "## Compatibility components", ""])
    for item in data["runtime_compatibility_components"]:
        lines.append(
            f"- `{item['component']}`: owner `{item['owner']}`, replacement "
            f"{item['replacement']}, expiry {item['expiry']}"
        )
    lines.extend(
        [
            "",
            "## Gate contract",
            "",
            "Every observed file/category fingerprint must have one versioned exemption "
            "with owner, reason, consumers, replacement, removal condition, regression "
            "test and issue reference. New or stale fingerprints fail CI. Shared-private "
            "and root-module fingerprints must match the reviewed baseline.",
            "",
        ]
    )
    return "\n".join(lines)


def validate(data: dict[str, Any], exemptions: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    observed = {str(row["id"]): row for row in data["violations"]}
    registered: dict[str, dict[str, Any]] = {}
    for row in exemptions.get("exceptions", []):
        missing = sorted(REQUIRED_EXCEPTION_FIELDS - set(row))
        if missing:
            errors.append(f"exemption missing fields {missing}: {row.get('id', '<missing>')}")
            continue
        row_id = str(row["id"])
        if row_id in registered:
            errors.append(f"duplicate exemption id: {row_id}")
        registered[row_id] = row
        if not isinstance(row["consumers"], list) or not row["consumers"]:
            errors.append(f"exemption consumers must be non-empty: {row_id}")
        for field in REQUIRED_EXCEPTION_FIELDS - {"id", "consumers"}:
            if not str(row[field]).strip():
                errors.append(f"empty exemption field {field}: {row_id}")
        if not str(row["issue"]).startswith("#"):
            errors.append(f"invalid exemption issue: {row_id}")
    for row_id, violation in observed.items():
        if row_id not in registered:
            errors.append(
                f"unregistered architecture violation {row_id}: "
                f"{violation['category']} {violation['path']} {violation['summary']}"
            )
    for row_id in sorted(set(registered) - set(observed)):
        errors.append(f"stale architecture exemption: {row_id}")
    shared = data["shared_contract_summary"]
    if int(shared["blocking_private_contract_access_count"]) != 0:
        errors.append(
            f"blocking private contracts detected: {shared['blocking_private_contract_access_count']}"
        )
    if str(exemptions.get("shared_private_access_sha256", "")) != str(
        shared["private_access_sha256"]
    ):
        errors.append("shared private access fingerprint changed")
    if str(exemptions.get("root_module_sha256", "")) != str(data["root_module_sha256"]):
        errors.append("root module fingerprint changed; classify #463 migration")
    if int(data["root_unclassified_count"]) != 0:
        errors.append(f"unclassified root modules: {data['root_unclassified_count']}")
    if int(data["router_duplicate_count"]) != 0:
        errors.append(f"duplicate Router registrations: {data['router_duplicate_count']}")
    return errors


def _paths(output_dir: Path) -> tuple[Path, Path, Path]:
    if output_dir == DOCS:
        return INVENTORY_JSON, INVENTORY_MD, EXEMPTIONS_JSON
    return (
        output_dir / INVENTORY_JSON.name,
        output_dir / INVENTORY_MD.name,
        output_dir / EXEMPTIONS_JSON.name,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory package-wide architecture drift")
    parser.add_argument("--label", default="working-tree")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--bootstrap-exemptions", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DOCS)
    args = parser.parse_args(argv)

    data = build_inventory(label=args.label)
    inventory_json, inventory_md, exemptions_path = _paths(args.output_dir)
    exemptions = (
        build_exemptions(data, label=args.label)
        if args.bootstrap_exemptions
        else _json(exemptions_path)
        if exemptions_path.is_file()
        else {"schema_version": 1, "exceptions": []}
    )
    encoded = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    exemption_encoded = json.dumps(exemptions, ensure_ascii=False, indent=2) + "\n"
    markdown = render_markdown(data, exemptions)

    if args.write:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        inventory_json.write_text(encoded, encoding="utf-8")
        inventory_md.write_text(markdown, encoding="utf-8")
        if args.bootstrap_exemptions:
            exemptions_path.write_text(exemption_encoded, encoding="utf-8")
    if args.json:
        print(encoded, end="")
    if args.check:
        errors = validate(data, exemptions)
        if not inventory_json.is_file() or inventory_json.read_text(encoding="utf-8") != encoded:
            errors.append("package_architecture_inventory.json is stale")
        if not inventory_md.is_file() or inventory_md.read_text(encoding="utf-8") != markdown:
            errors.append("package_architecture_inventory.md is stale")
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
    if not args.write and not args.check and not args.json:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
