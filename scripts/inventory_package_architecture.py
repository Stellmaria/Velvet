from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"
DOCS = ROOT / "docs"
DEFAULT_INVENTORY_JSON = DOCS / "package_architecture_inventory.json"
DEFAULT_INVENTORY_MD = DOCS / "package_architecture_inventory.md"
DEFAULT_EXEMPTIONS = DOCS / "package_architecture_exemptions.json"
SHARED_INVENTORY = DOCS / "shared_contract_inventory.json"
ARCHITECTURE_INVENTORY = DOCS / "architecture_layout_inventory.json"
REPOSITORY_INVENTORY = DOCS / "repository_layout_inventory.json"
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


def _production_paths() -> tuple[Path, ...]:
    return tuple(sorted(path for path in PACKAGE.rglob("*.py") if "__pycache__" not in path.parts))


def _module_name(path: Path) -> str:
    relative = path.relative_to(ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _layer(path: Path) -> str:
    relative = path.relative_to(PACKAGE)
    if len(relative.parts) == 1:
        return "root"
    return LAYER_PREFIXES.get(relative.parts[0], "other")


def _target_package(path: Path, root_targets: dict[str, str]) -> str:
    module = _module_name(path)
    layer = _layer(path)
    if layer != "root":
        return layer
    category = root_targets.get(module, "unclassified")
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
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    if isinstance(node, ast.Subscript):
        return _dotted(node.value)
    return ""


def _resolve_import_from(current_module: str, level: int, module: str | None) -> str:
    if level <= 0:
        return module or ""
    parts = current_module.split(".")
    if parts and not current_module.endswith(".__init__"):
        parts = parts[:-1]
    keep = max(0, len(parts) - level + 1)
    prefix = parts[:keep]
    if module:
        prefix.extend(module.split("."))
    return ".".join(prefix)


def _imports(tree: ast.Module, current_module: str) -> tuple[dict[str, str], list[str]]:
    aliases: dict[str, str] = {}
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                aliases[local] = alias.name
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            source = _resolve_import_from(current_module, node.level, node.module)
            if source:
                modules.append(source)
            for alias in node.names:
                if alias.name == "*":
                    continue
                local = alias.asname or alias.name
                aliases[local] = f"{source}.{alias.name}" if source else alias.name
    return aliases, sorted(set(modules))


def _function_owner(tree: ast.Module, node: ast.AST) -> str:
    best_name = "<module>"
    best_span = 10**9
    line = int(getattr(node, "lineno", 0) or 0)
    for candidate in ast.walk(tree):
        if not isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        start = int(getattr(candidate, "lineno", 0) or 0)
        end = int(getattr(candidate, "end_lineno", start) or start)
        if start <= line <= end and end - start < best_span:
            best_name = candidate.name
            best_span = end - start
    return best_name


def _stable_id(category: str, path: str, symbol: str) -> str:
    normalized = " ".join(symbol.split())
    digest = hashlib.sha256(f"{category}\n{path}\n{normalized}".encode("utf-8")).hexdigest()[:16]
    return f"{category}:{path}:{digest}"


def _violation(
    category: str,
    path: str,
    symbol: str,
    *,
    line: int | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": _stable_id(category, path, symbol),
        "category": category,
        "path": path,
        "line": line,
        "symbol": symbol,
        "details": details or {},
    }


def _persistence_path(path: Path) -> bool:
    stem = path.stem.casefold()
    parts = {part.casefold() for part in path.parts}
    return (
        any(token in stem for token in ("repository", "queries", "query", "store", "database", "persistence"))
        or "migrations" in parts
        or "repositories" in parts
    )


def _scan_module(path: Path, root_targets: dict[str, str]) -> dict[str, Any]:
    relative = path.relative_to(ROOT).as_posix()
    module = _module_name(path)
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, filename=relative)
    aliases, import_modules = _imports(tree, module)
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    classes = [node for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    handlers = [
        node
        for node in functions
        if any(
            any(token in _dotted(decorator) for token in (".message", ".callback_query", ".inline_query"))
            for decorator in node.decorator_list
        )
    ]
    max_function_length = max(
        (
            int(getattr(node, "end_lineno", node.lineno) or node.lineno) - int(node.lineno) + 1
            for node in functions
        ),
        default=0,
    )
    aliases_by_root = {name: origin for name, origin in aliases.items()}
    foreign_assignments: list[dict[str, Any]] = []
    sql_literals: list[dict[str, Any]] = []
    acquire_calls: list[dict[str, Any]] = []
    dynamic_imports: list[dict[str, Any]] = []
    env_reads: list[dict[str, Any]] = []
    polling_values: list[dict[str, Any]] = []
    install_definitions: list[str] = []
    install_calls: list[dict[str, Any]] = []
    any_count = 0
    cast_count = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "Any":
            any_count += 1
        if isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            if dotted in {"cast", "typing.cast"} or dotted.endswith(".cast"):
                cast_count += 1
            if dotted in {"importlib.import_module", "__import__"}:
                dynamic_imports.append(
                    {"line": node.lineno, "call": dotted, "owner": _function_owner(tree, node)}
                )
            if dotted.endswith(".acquire"):
                acquire_calls.append(
                    {"line": node.lineno, "call": dotted, "owner": _function_owner(tree, node)}
                )
            if dotted in {"os.getenv", "os.environ.get", "environ.get"} or dotted.endswith(".getenv"):
                env_reads.append(
                    {"line": node.lineno, "call": dotted, "owner": _function_owner(tree, node)}
                )
            if dotted.endswith("sleep") or "poll" in dotted.casefold():
                constants = [
                    value.value
                    for value in ast.walk(node)
                    if isinstance(value, ast.Constant) and isinstance(value.value, (int, float))
                ]
                if constants:
                    polling_values.append(
                        {"line": node.lineno, "call": dotted, "values": constants}
                    )
            if dotted.split(".")[-1].startswith("install_"):
                install_calls.append({"line": node.lineno, "call": dotted})
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("install_"):
            install_definitions.append(node.name)
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            match = SQL_PATTERN.search(node.value)
            if match:
                normalized = " ".join(node.value.split())[:180]
                sql_literals.append(
                    {
                        "line": node.lineno,
                        "keyword": match.group(1).upper(),
                        "owner": _function_owner(tree, node),
                        "preview": normalized,
                    }
                )
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            else:
                targets = [node.target]
            for target in targets:
                if not isinstance(target, ast.Attribute):
                    continue
                dotted_target = _dotted(target)
                root_name = dotted_target.split(".", 1)[0]
                if root_name not in aliases_by_root:
                    continue
                foreign_assignments.append(
                    {
                        "line": target.lineno,
                        "target": dotted_target,
                        "origin": aliases_by_root[root_name],
                        "owner": _function_owner(tree, target),
                    }
                )

    layer = _layer(path)
    type_ignore_count = sum("# type: ignore" in line for line in lines)
    method_assign_ignore_count = sum("type: ignore[method-assign]" in line for line in lines)
    installed_sentinel_count = sum("_INSTALLED" in line for line in lines)
    package_getattr = any(node.name == "__getattr__" for node in functions)
    aiogram_imports = sorted(module_name for module_name in import_modules if module_name == "aiogram" or module_name.startswith("aiogram."))

    violations: list[dict[str, Any]] = []
    if layer in {"domain", "service"} and aiogram_imports:
        violations.append(
            _violation(
                "domain-aiogram-import",
                relative,
                ",".join(aiogram_imports),
                details={"layer": layer, "imports": aiogram_imports},
            )
        )
    forbidden_imports = sorted(
        imported
        for imported in import_modules
        if layer == "domain"
        and imported.startswith(("velvet_bot.presentation", "velvet_bot.app"))
    )
    if forbidden_imports:
        violations.append(
            _violation(
                "domain-layer-import",
                relative,
                ",".join(forbidden_imports),
                details={"imports": forbidden_imports},
            )
        )
    if sql_literals and not _persistence_path(path):
        for item in sql_literals:
            symbol = f"{item['owner']}:{item['keyword']}:{item['preview']}"
            violations.append(
                _violation("sql-outside-persistence", relative, symbol, line=item["line"], details=item)
            )
    if acquire_calls and not _persistence_path(path):
        for item in acquire_calls:
            symbol = f"{item['owner']}:{item['call']}"
            violations.append(
                _violation("database-acquire-outside-persistence", relative, symbol, line=item["line"], details=item)
            )
    for item in foreign_assignments:
        symbol = f"{item['owner']}:{item['target']}:{item['origin']}"
        violations.append(
            _violation("foreign-assignment", relative, symbol, line=item["line"], details=item)
        )
    for item in dynamic_imports:
        symbol = f"{item['owner']}:{item['call']}"
        violations.append(
            _violation("dynamic-import", relative, symbol, line=item["line"], details=item)
        )
    if path.name.endswith(INSTALL_FILE_SUFFIXES):
        violations.append(
            _violation("installer-like-module", relative, path.name, details={"suffixes": INSTALL_FILE_SUFFIXES})
        )
    if method_assign_ignore_count:
        violations.append(
            _violation(
                "method-assign-ignore",
                relative,
                f"count={method_assign_ignore_count}",
                details={"count": method_assign_ignore_count},
            )
        )
    if package_getattr:
        violations.append(_violation("package-getattr-side-effect", relative, "__getattr__"))
    if installed_sentinel_count:
        violations.append(
            _violation(
                "installed-sentinel",
                relative,
                f"_INSTALLED-count={installed_sentinel_count}",
                details={"count": installed_sentinel_count},
            )
        )
    if len(lines) > MONOLITH_LOC_LIMIT:
        violations.append(
            _violation(
                "monolithic-module-loc",
                relative,
                f"loc={len(lines)}",
                details={"loc": len(lines), "limit": MONOLITH_LOC_LIMIT},
            )
        )
    if max_function_length > MONOLITH_FUNCTION_LIMIT:
        violations.append(
            _violation(
                "monolithic-function",
                relative,
                f"max-function-lines={max_function_length}",
                details={"max_function_length": max_function_length, "limit": MONOLITH_FUNCTION_LIMIT},
            )
        )

    return {
        "path": relative,
        "module": module,
        "layer": layer,
        "target_package": _target_package(path, root_targets),
        "loc": len(lines),
        "function_count": len(functions),
        "class_count": len(classes),
        "handler_count": len(handlers),
        "max_function_length": max_function_length,
        "imports": import_modules,
        "aiogram_imports": aiogram_imports,
        "sql_literal_count": len(sql_literals),
        "database_acquire_count": len(acquire_calls),
        "private_any_count": any_count,
        "cast_count": cast_count,
        "type_ignore_count": type_ignore_count,
        "method_assign_ignore_count": method_assign_ignore_count,
        "dynamic_imports": dynamic_imports,
        "foreign_assignments": foreign_assignments,
        "install_definitions": sorted(install_definitions),
        "install_calls": install_calls,
        "installed_sentinel_count": installed_sentinel_count,
        "package_getattr": package_getattr,
        "env_reads": env_reads,
        "polling_values": polling_values,
        "violations": violations,
    }


def _load_root_targets() -> tuple[dict[str, str], dict[str, Any]]:
    namespace: dict[str, Any] = {}
    exec(compile(ROOT_INVENTORY_SCRIPT.read_text(encoding="utf-8"), str(ROOT_INVENTORY_SCRIPT), "exec"), namespace)
    data = namespace["build_inventory"]()
    targets = {str(entry["module"]): str(entry["category"]) for entry in data["entries"]}
    return targets, data


def _reverse_consumers(modules: list[dict[str, Any]]) -> dict[str, list[str]]:
    consumers: defaultdict[str, set[str]] = defaultdict(set)
    for item in modules:
        path = str(item["path"])
        for imported in item["imports"]:
            consumers[str(imported)].add(path)
    return {module: sorted(paths) for module, paths in consumers.items()}


def _installer_graph(modules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_module = {str(item["module"]): item for item in modules}
    app_init = by_module.get("velvet_bot.app")
    if app_init is None:
        return []
    path = ROOT / str(app_init["path"])
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    aliases, _ = _imports(tree, "velvet_bot.app.__init__")
    graph: list[dict[str, Any]] = []
    for call in sorted(app_init["install_calls"], key=lambda row: int(row["line"])):
        local = str(call["call"]).split(".")[0]
        origin = aliases.get(local, local)
        owner_module = origin.rsplit(".", 1)[0] if "." in origin else origin
        owner_entry = by_module.get(owner_module, {})
        patched = [
            str(item["target"])
            for item in owner_entry.get("foreign_assignments", [])
        ]
        graph.append(
            {
                "order": len(graph) + 1,
                "line": int(call["line"]),
                "call": str(call["call"]),
                "origin": origin,
                "owner_module": owner_module,
                "patched_symbols": sorted(set(patched)),
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
    return hashlib.sha256("\n".join(sorted(rows)).encode("utf-8")).hexdigest()


def _suggest_exception(violation: dict[str, Any], consumers: dict[str, list[str]]) -> dict[str, Any]:
    path = str(violation["path"])
    category = str(violation["category"])
    lowered = path.casefold()
    if "media_generation" in lowered or "delivery" in lowered or "grs" in lowered:
        issue = "#457" if "delivery" in lowered or "worker" in lowered else "#459"
    elif "auf" in lowered and category in {"sql-outside-persistence", "monolithic-module-loc", "monolithic-function"}:
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
    owner = {
        "#455": "application-composition",
        "#457": "media-delivery",
        "#458": "auf-application-presentation",
        "#459": "provider-adapters",
        "#460": "architecture-governance",
        "#463": "root-module-migration",
    }[issue]
    module = str(violation.get("details", {}).get("origin", "")).rsplit(".", 1)[0]
    consumer_rows = consumers.get(module, []) if module else []
    if not consumer_rows:
        consumer_rows = [path]
    return {
        "id": str(violation["id"]),
        "owner": owner,
        "reason": f"Existing {category} debt captured by the package-wide baseline.",
        "consumers": consumer_rows,
        "replacement": f"Canonical boundary tracked by {issue}.",
        "removal_condition": f"Remove this exemption when {issue} retires the recorded debt without behavior regression.",
        "regression_test": "tests/test_package_architecture_inventory.py",
        "issue": issue,
    }


def build_inventory(*, label: str = "working-tree") -> dict[str, Any]:
    root_targets, root_inventory = _load_root_targets()
    modules = [_scan_module(path, root_targets) for path in _production_paths()]
    consumers = _reverse_consumers(modules)
    violations = [violation for item in modules for violation in item["violations"]]
    architecture = _json(ARCHITECTURE_INVENTORY)
    repository = _json(REPOSITORY_INVENTORY)
    shared = _json(SHARED_INVENTORY)
    compatibility = [
        {
            "component": component,
            "owner": "runtime-compatibility",
            "replacement": "Explicit composition registration or removal regression.",
            "expiry": "Retire after consumers migrate under #420/#455.",
            "issue": "#420",
        }
        for component in (
            list(architecture.get("pre_import_compatibility_components", []))
            + list(architecture.get("post_import_compatibility_components", []))
        )
    ]
    layer_counts = Counter(str(item["layer"]) for item in modules)
    violation_counts = Counter(str(item["category"]) for item in violations)
    return {
        "schema_version": 1,
        "generated_from": label,
        "production_module_count": len(modules),
        "production_loc": sum(int(item["loc"]) for item in modules),
        "layer_counts": dict(sorted(layer_counts.items())),
        "root_module_count": int(root_inventory["root_module_count"]),
        "root_module_sha256": str(root_inventory["root_module_name_sha256"]),
        "root_unclassified_count": int(root_inventory["unclassified_count"]),
        "router_count": int(architecture["active_bundle_router_count"]),
        "router_duplicate_count": int(architecture["duplicate_bundle_router_import_count"]),
        "repository_module_count": int(repository["repository_module_count"]),
        "runtime_compatibility_components": compatibility,
        "shared_contract_summary": {
            "production_python_files": int(shared["production_python_files"]),
            "function_count": int(shared["function_count"]),
            "private_contract_access_count": int(shared["private_contract_access_count"]),
            "blocking_private_contract_access_count": int(shared["blocking_private_contract_access_count"]),
            "exact_duplicate_group_count": int(shared["exact_duplicate_group_count"]),
            "normalized_duplicate_group_count": int(shared["normalized_duplicate_group_count"]),
            "semantic_near_duplicate_group_count": int(shared["semantic_near_duplicate_group_count"]),
            "private_access_sha256": _shared_fingerprint(shared),
        },
        "installer_graph": _installer_graph(modules),
        "violation_count": len(violations),
        "violation_counts": dict(sorted(violation_counts.items())),
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
        "shared_private_access_sha256": data["shared_contract_summary"]["private_access_sha256"],
        "root_module_sha256": data["root_module_sha256"],
        "exceptions": sorted(exceptions, key=lambda row: str(row["id"])),
    }


def render_markdown(data: dict[str, Any], exemptions: dict[str, Any]) -> str:
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
    for layer, count in data["layer_counts"].items():
        lines.append(f"- `{layer}`: **{count}** modules")
    lines.extend(["", "## Shared/private baseline", ""])
    shared = data["shared_contract_summary"]
    lines.extend(
        [
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
    for category, count in data["violation_counts"].items():
        lines.append(f"- `{category}`: **{count}**")
    lines.extend(["", "## Largest modules", ""])
    largest = sorted(data["modules"], key=lambda row: int(row["loc"]), reverse=True)[:20]
    for item in largest:
        lines.append(
            f"- `{item['path']}`: {item['loc']} LOC, {item['function_count']} functions, max function {item['max_function_length']} lines, target `{item['target_package']}`."
        )
    lines.extend(["", "## Compatibility components", ""])
    for item in data["runtime_compatibility_components"]:
        lines.append(
            f"- `{item['component']}`: owner `{item['owner']}`, replacement {item['replacement']}, expiry {item['expiry']}"
        )
    lines.extend(
        [
            "",
            "## Gate contract",
            "",
            "Every observed violation ID must have one versioned exemption with owner, reason, consumers, replacement, removal condition, regression test and issue reference. New or stale IDs fail CI. Shared-private and root-module fingerprints must match the reviewed baseline.",
            "",
        ]
    )
    return "\n".join(lines)


def validate(data: dict[str, Any], exemptions: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    observed = {str(item["id"]): item for item in data["violations"]}
    rows = list(exemptions.get("exceptions", []))
    registered: dict[str, dict[str, Any]] = {}
    for row in rows:
        missing = sorted(REQUIRED_EXCEPTION_FIELDS - set(row))
        if missing:
            errors.append(f"exemption missing fields {missing}: {row.get('id', '<missing-id>')}")
            continue
        row_id = str(row["id"])
        if row_id in registered:
            errors.append(f"duplicate exemption id: {row_id}")
        registered[row_id] = row
        if not isinstance(row["consumers"], list) or not row["consumers"]:
            errors.append(f"exemption consumers must be a non-empty list: {row_id}")
        for field in REQUIRED_EXCEPTION_FIELDS - {"id", "consumers"}:
            if not str(row[field]).strip():
                errors.append(f"exemption field {field} is empty: {row_id}")
        if not str(row["issue"]).startswith("#"):
            errors.append(f"exemption issue must be a GitHub issue reference: {row_id}")
    for row_id, violation in observed.items():
        if row_id not in registered:
            errors.append(
                f"unregistered architecture violation {row_id}: {violation['category']} {violation['path']} {violation['symbol']}"
            )
    for row_id in sorted(set(registered) - set(observed)):
        errors.append(f"stale architecture exemption without observed violation: {row_id}")
    shared = data["shared_contract_summary"]
    if int(shared["blocking_private_contract_access_count"]) != 0:
        errors.append(
            f"blocking private contracts detected: {shared['blocking_private_contract_access_count']}"
        )
    if str(exemptions.get("shared_private_access_sha256", "")) != str(shared["private_access_sha256"]):
        errors.append("shared private access fingerprint changed; review and update #460 baseline")
    if str(exemptions.get("root_module_sha256", "")) != str(data["root_module_sha256"]):
        errors.append("root module fingerprint changed; classify the #463 migration before updating baseline")
    if int(data["root_unclassified_count"]) != 0:
        errors.append(f"unclassified root modules: {data['root_unclassified_count']}")
    if int(data["router_duplicate_count"]) != 0:
        errors.append(f"duplicate Router registrations: {data['router_duplicate_count']}")
    return errors


def _paths(output_dir: Path) -> tuple[Path, Path, Path]:
    if output_dir == DOCS:
        return DEFAULT_INVENTORY_JSON, DEFAULT_INVENTORY_MD, DEFAULT_EXEMPTIONS
    return (
        output_dir / DEFAULT_INVENTORY_JSON.name,
        output_dir / DEFAULT_INVENTORY_MD.name,
        output_dir / DEFAULT_EXEMPTIONS.name,
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
    if args.bootstrap_exemptions:
        exemptions = build_exemptions(data, label=args.label)
    elif exemptions_path.is_file():
        exemptions = _json(exemptions_path)
    else:
        exemptions = {"schema_version": 1, "exceptions": []}

    markdown = render_markdown(data, exemptions)
    encoded = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    exemption_encoded = json.dumps(exemptions, ensure_ascii=False, indent=2) + "\n"

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
