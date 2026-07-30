from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"
SHARED_ROOT = PACKAGE / "presentation" / "telegram" / "shared"

DuplicateKind = Literal[
    "real-duplicate",
    "normalized-near-duplicate",
    "semantic-near-duplicate",
    "generated/compat",
    "allowed-template",
]

SQL_PATTERN = re.compile(
    r"(?:\bSELECT\b.+\bFROM\b|\bINSERT\s+INTO\b|\bUPDATE\b.+\bSET\b|\bDELETE\s+FROM\b)",
    re.IGNORECASE | re.DOTALL,
)
FORBIDDEN_SHARED_IMPORT_PREFIXES = (
    "velvet_bot.database",
    "velvet_bot.domains",
    "velvet_bot.repositories",
)
TEMPORARY_TARGET_MARKERS = (
    "hotfix",
    "active_delivery_fix",
    "_install",
    ".install",
)
PRIVATE_CONTRACT_TOKENS = (
    "edit",
    "task",
    "model",
    "reference",
    "validated",
    "wallet",
    "delivery",
    "deliver",
    "result",
    "retry",
    "state",
    "mapping",
    "callback",
    "keyboard",
    "line",
    "load",
    "build",
    "format",
    "send",
    "truncate",
    "budget",
    "require",
    "settings",
    "progress",
    "download",
    "preview",
    "original",
    "wan_mode",
)


@dataclass(frozen=True, slots=True)
class SharedContract:
    family: str
    current_owner: str
    target_contract: str
    target_issue: str
    retirement_issue: str
    status: Literal["canonical", "transitional", "inventory-only"]
    public_symbols: tuple[str, ...]
    notes: str


CONTRACTS: tuple[SharedContract, ...] = (
    SharedContract(
        family="safe edit/send fallback",
        current_owner="velvet_bot.presentation.telegram.shared.editing",
        target_contract="velvet_bot.presentation.telegram.shared.editing",
        target_issue="#419",
        retirement_issue="#419",
        status="canonical",
        public_symbols=("safe_edit_message_text", "safe_edit_callback_text"),
        notes="Suppress only Telegram's unchanged-message response.",
    ),
    SharedContract(
        family="pagination keyboards",
        current_owner="controller-local keyboard builders",
        target_contract="velvet_bot.presentation.telegram.shared.navigation",
        target_issue="#419",
        retirement_issue="#419",
        status="transitional",
        public_symbols=("build_pagination_keyboard", "build_navigation_keyboard"),
        notes="Caller owns callback payload and domain navigation decisions.",
    ),
    SharedContract(
        family="deletion helpers",
        current_owner="velvet_bot.presentation.telegram.message_deletion",
        target_contract="velvet_bot.presentation.telegram.shared.deletion",
        target_issue="#419",
        retirement_issue="#419",
        status="transitional",
        public_symbols=("delete_message_safely", "is_message_already_absent"),
        notes="Suppress only already-absent/not-found Telegram responses.",
    ),
    SharedContract(
        family="media download/preview/original delivery",
        current_owner="velvet_bot.domains.media_generation.file_delivery_worker",
        target_contract="velvet_bot.domains.media_generation.delivery_pipeline",
        target_issue="#457",
        retirement_issue="#457",
        status="transitional",
        public_symbols=("download_telegram_file",),
        notes="App delivery fixes are consumers, never canonical targets.",
    ),
    SharedContract(
        family="callback navigation and back buttons",
        current_owner="controller-local keyboard builders",
        target_contract="velvet_bot.presentation.telegram.shared.navigation",
        target_issue="#419",
        retirement_issue="#419",
        status="transitional",
        public_symbols=("build_back_refresh_keyboard", "NavigationButton"),
        notes="Shared layer receives callback data from the caller.",
    ),
    SharedContract(
        family="owner/editor/member guards",
        current_owner="velvet_bot.core.access",
        target_contract="velvet_bot.core.access",
        target_issue="#419",
        retirement_issue="#460",
        status="canonical",
        public_symbols=("AccessPolicy",),
        notes="Permissions remain outside generic Telegram helpers.",
    ),
    SharedContract(
        family="worker compensation/reporting boilerplate",
        current_owner="velvet_bot.domains.media_generation.worker",
        target_contract="velvet_bot.domains.media_generation.worker",
        target_issue="#419",
        retirement_issue="#457",
        status="canonical",
        public_symbols=("KieGenerationWorker",),
        notes="Worker lifecycle owns compensation and terminal reporting.",
    ),
    SharedContract(
        family="message chunking/HTML fallback",
        current_owner="controller-local long-message senders",
        target_contract="velvet_bot.presentation.telegram.shared.text",
        target_issue="#419",
        retirement_issue="#419",
        status="transitional",
        public_symbols=("chunk_telegram_text", "answer_text_chunks"),
        notes="Transport length and parse fallback only.",
    ),
    SharedContract(
        family="repeated progress-card updates",
        current_owner="velvet_bot.app.telegram_progress_resilience",
        target_contract="velvet_bot.presentation.telegram.progress",
        target_issue="#419",
        retirement_issue="#455",
        status="transitional",
        public_symbols=("render_progress_bar",),
        notes="Task execution must remain independent from progress editing.",
    ),
    SharedContract(
        family="task payload/result mapping/formatting",
        current_owner="Auf portal and delivery recovery installers",
        target_contract="velvet_bot.application.media_tasks.contracts",
        target_issue="#458",
        retirement_issue="#458",
        status="inventory-only",
        public_symbols=("task_payload_mapping", "task_result_urls"),
        notes="Application mapping contract; not Telegram shared UI.",
    ),
    SharedContract(
        family="provider/model labels",
        current_owner="router-local model dictionaries",
        target_contract="velvet_bot.domains.media_generation.models",
        target_issue="#459",
        retirement_issue="#459",
        status="inventory-only",
        public_symbols=("KieModelAlias", "display_name"),
        notes="Provider catalog owns labels and identifiers.",
    ),
    SharedContract(
        family="state compatibility accessors",
        current_owner="Auf portal compatibility reads",
        target_contract="velvet_bot.presentation.telegram.state_compatibility",
        target_issue="#419",
        retirement_issue="#438",
        status="transitional",
        public_symbols=("state_value",),
        notes="Compatibility has explicit retirement after z024 acceptance.",
    ),
    SharedContract(
        family="retry/backoff policies",
        current_owner="media workers and Auf delivery recovery",
        target_contract="velvet_bot.presentation.telegram.shared.retry",
        target_issue="#419",
        retirement_issue="#457",
        status="transitional",
        public_symbols=("TelegramRetryPolicy", "retry_telegram_operation"),
        notes="Typed Telegram retry policy; no broad exception injection.",
    ),
    SharedContract(
        family="workspace task history/ownership queries",
        current_owner="velvet_bot.app.auf_user_portal_install",
        target_contract="velvet_bot.application.workspace_tasks",
        target_issue="#458",
        retirement_issue="#458",
        status="inventory-only",
        public_symbols=("list_owned_workspace_tasks", "get_owned_success_task"),
        notes="SQL moves to application/repository boundary, never shared presentation.",
    ),
)
CONTRACT_BY_FAMILY = {item.family: item for item in CONTRACTS}


@dataclass(frozen=True, slots=True)
class KnownPrivateContract:
    source_module: str
    private_name: str
    public_name: str
    family: str
    retirement_issue: str


KNOWN_PRIVATE_CONTRACTS: tuple[KnownPrivateContract, ...] = (
    KnownPrivateContract(
        "velvet_bot.app.auf_user_portal_install",
        "_task_line",
        "format_user_task_line",
        "task payload/result mapping/formatting",
        "#458",
    ),
    KnownPrivateContract(
        "velvet_bot.app.auf_user_portal_install",
        "_load_user_tasks",
        "load_user_tasks",
        "workspace task history/ownership queries",
        "#458",
    ),
    KnownPrivateContract(
        "velvet_bot.app.auf_user_portal_install",
        "_task_list_keyboard",
        "build_user_task_list_keyboard",
        "pagination keyboards",
        "#458",
    ),
    KnownPrivateContract(
        "velvet_bot.app.auf_user_portal_install",
        "_MODEL_NAMES",
        "MODEL_NAMES",
        "provider/model labels",
        "#459",
    ),
    KnownPrivateContract(
        "velvet_bot.presentation.telegram.routers.workspace_auf_video",
        "_edit_or_answer",
        "edit_or_answer",
        "safe edit/send fallback",
        "#419",
    ),
    KnownPrivateContract(
        "velvet_bot.presentation.telegram.routers.workspace_auf_video_simple",
        "_validated_model",
        "validated_model",
        "task payload/result mapping/formatting",
        "#458",
    ),
    KnownPrivateContract(
        "velvet_bot.presentation.telegram.routers.workspace_auf_video",
        "_reference_from_data",
        "reference_from_data",
        "task payload/result mapping/formatting",
        "#458",
    ),
)
KNOWN_PRIVATE_NAMES = {item.private_name for item in KNOWN_PRIVATE_CONTRACTS}


@dataclass(frozen=True, slots=True)
class FunctionOccurrence:
    path: str
    module: str
    name: str
    line: int
    end_line: int
    exact_digest: str
    normalized_digest: str
    calls: tuple[str, ...]
    attributes: tuple[str, ...]
    text_markers: tuple[str, ...]
    node_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DuplicateGroup:
    digest: str
    kind: DuplicateKind
    family: str
    occurrences: tuple[FunctionOccurrence, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class PrivateContractAccess:
    path: str
    module: str
    line: int
    source_module: str
    private_name: str
    access_kind: Literal["direct-import", "module-attribute", "getattr", "assignment"]
    expression: str
    family: str


@dataclass(frozen=True, slots=True)
class ImportContext:
    module_aliases: dict[str, str]
    symbol_origins: dict[str, tuple[str, str]]


class _Normalizer(ast.NodeTransformer):
    _ATTRIBUTE_NORMALIZATION = {
        "send_photo": "send_media",
        "send_video": "send_media",
        "_send_image_and_document": "send_media_and_document",
        "_send_video_and_document": "send_media_and_document",
        "image": "media",
        "video": "media",
    }

    def __init__(self) -> None:
        self._names: dict[str, str] = {}

    def _name(self, value: str) -> str:
        if value in {
            "self",
            "cls",
            "True",
            "False",
            "None",
            "Exception",
            "BaseException",
        }:
            return value
        if value not in self._names:
            self._names[value] = f"v{len(self._names)}"
        return self._names[value]

    def visit_Name(self, node: ast.Name) -> ast.AST:
        return ast.copy_location(ast.Name(id=self._name(node.id), ctx=node.ctx), node)

    def visit_arg(self, node: ast.arg) -> ast.AST:
        return ast.copy_location(
            ast.arg(arg=self._name(node.arg), annotation=self.visit(node.annotation)),
            node,
        )

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        value = node.value
        if isinstance(value, str):
            normalized: object = "<str>"
        elif isinstance(value, bytes):
            normalized = b"<bytes>"
        elif isinstance(value, bool) or value is None:
            normalized = value
        elif isinstance(value, (int, float, complex)):
            normalized = 0
        else:
            normalized = f"<{type(value).__name__}>"
        return ast.copy_location(ast.Constant(value=normalized), node)

    def visit_Attribute(self, node: ast.Attribute) -> ast.AST:
        value = self.visit(node.value)
        attr = self._ATTRIBUTE_NORMALIZATION.get(node.attr, node.attr)
        return ast.copy_location(ast.Attribute(value=value, attr=attr, ctx=node.ctx), node)


def _python_paths() -> tuple[Path, ...]:
    return tuple(
        path
        for path in sorted(PACKAGE.rglob("*.py"))
        if "__pycache__" not in path.parts
    )


def _module_name(path: Path) -> str:
    return ".".join(path.relative_to(ROOT).with_suffix("").parts)


def _module_exists(module: str) -> bool:
    file_path = ROOT.joinpath(*module.split(".")).with_suffix(".py")
    package_path = ROOT.joinpath(*module.split("."), "__init__.py")
    return file_path.exists() or package_path.exists()


def _resolve_import(current_module: str, node: ast.ImportFrom) -> str:
    module = node.module or ""
    if node.level == 0:
        return module
    package = current_module.split(".")[:-1]
    keep = max(0, len(package) - node.level + 1)
    suffix = module.split(".") if module else []
    return ".".join((*package[:keep], *suffix))


def _importlib_target(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Call) or not node.args:
        return None
    function = node.func
    is_import_module = (
        isinstance(function, ast.Attribute)
        and isinstance(function.value, ast.Name)
        and function.value.id == "importlib"
        and function.attr == "import_module"
    ) or (isinstance(function, ast.Name) and function.id == "import_module")
    if not is_import_module:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _collect_import_context(
    current_module: str,
    tree: ast.AST,
) -> ImportContext:
    module_aliases: dict[str, str] = {}
    symbol_origins: dict[str, tuple[str, str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".", 1)[0]
                module_aliases[local] = alias.name
        elif isinstance(node, ast.ImportFrom):
            source = _resolve_import(current_module, node)
            for alias in node.names:
                local = alias.asname or alias.name
                candidate = f"{source}.{alias.name}" if source else alias.name
                if _module_exists(candidate):
                    module_aliases[local] = candidate
                else:
                    symbol_origins[local] = (source, alias.name)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            target_module = _importlib_target(value) if value is not None else None
            if target_module is None:
                continue
            targets: list[ast.AST]
            if isinstance(node, ast.Assign):
                targets = list(node.targets)
            else:
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    module_aliases[target.id] = target_module
    return ImportContext(module_aliases=module_aliases, symbol_origins=symbol_origins)


def _attribute_chain(node: ast.Attribute) -> tuple[str | None, tuple[str, ...]]:
    attributes: list[str] = [node.attr]
    value: ast.AST = node.value
    while isinstance(value, ast.Attribute):
        attributes.append(value.attr)
        value = value.value
    if not isinstance(value, ast.Name):
        return None, tuple(reversed(attributes))
    return value.id, tuple(reversed(attributes))


def _looks_like_private_contract(name: str) -> bool:
    if not name.startswith("_") or name.startswith("__"):
        return False
    if name in KNOWN_PRIVATE_NAMES:
        return True
    normalized = name.casefold()
    return any(token in normalized for token in PRIVATE_CONTRACT_TOKENS)


def _family_from_text(value: str) -> str:
    text = value.casefold()
    mappings = (
        ("safe edit/send fallback", ("edit_or_answer", "safe_edit", "edit_text")),
        ("pagination keyboards", ("pager", "pagination", "task_list_keyboard", "page_keyboard")),
        ("deletion helpers", ("delete_message", "safe_delete", "deletion")),
        (
            "media download/preview/original delivery",
            ("deliver", "delivery", "download_result", "preview", "original", "result_filename"),
        ),
        ("callback navigation and back buttons", ("back_keyboard", "navigation", "callback")),
        ("owner/editor/member guards", ("require_", "owner_guard", "member_guard", "access")),
        ("worker compensation/reporting boilerplate", ("compens", "report_failure", "terminal_failure")),
        ("message chunking/HTML fallback", ("chunk", "split_message", "html_fallback")),
        ("repeated progress-card updates", ("progress", "status_card")),
        ("task payload/result mapping/formatting", ("mapping", "payload", "result_urls", "task_line")),
        ("provider/model labels", ("model_names", "model_alias", "display_name")),
        ("state compatibility accessors", ("state_value", "auf_", "meow_")),
        ("retry/backoff policies", ("retry", "backoff", "retry_delay")),
        ("workspace task history/ownership queries", ("load_user_tasks", "owned_success_task", "task_history")),
    )
    for family, markers in mappings:
        if any(marker in text for marker in markers):
            return family
    return "other repeated implementation"


def _resolve_attribute_source(
    *,
    root: str,
    intermediate: Sequence[str],
    context: ImportContext,
    contexts: dict[str, ImportContext],
) -> str | None:
    if root in context.module_aliases:
        current = context.module_aliases[root]
    elif root in context.symbol_origins:
        module, symbol = context.symbol_origins[root]
        current = f"{module}.{symbol}" if module else symbol
    else:
        return None
    for item in intermediate:
        current_context = contexts.get(current)
        if current_context is not None and item in current_context.module_aliases:
            current = current_context.module_aliases[item]
            continue
        candidate = f"{current}.{item}"
        if _module_exists(candidate):
            current = candidate
        else:
            current = candidate
    return current


def _private_accesses(
    paths: tuple[Path, ...],
    trees: dict[str, ast.AST],
    contexts: dict[str, ImportContext],
) -> tuple[PrivateContractAccess, ...]:
    found: dict[tuple[str, int, str, str, str], PrivateContractAccess] = {}
    for path in paths:
        module = _module_name(path)
        tree = trees[module]
        context = contexts[module]
        relative = path.relative_to(ROOT).as_posix()

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                source = _resolve_import(module, node)
                for alias in node.names:
                    if not _looks_like_private_contract(alias.name):
                        continue
                    access = PrivateContractAccess(
                        path=relative,
                        module=module,
                        line=node.lineno,
                        source_module=source,
                        private_name=alias.name,
                        access_kind="direct-import",
                        expression=f"from {source} import {alias.name}",
                        family=_family_from_text(f"{source} {alias.name}"),
                    )
                    found[(relative, node.lineno, source, alias.name, "direct-import")] = access
            elif isinstance(node, ast.Attribute):
                if not _looks_like_private_contract(node.attr):
                    continue
                root, attributes = _attribute_chain(node)
                if root is None:
                    continue
                source = _resolve_attribute_source(
                    root=root,
                    intermediate=attributes[:-1],
                    context=context,
                    contexts=contexts,
                )
                if source is None or source == module:
                    continue
                kind: Literal["module-attribute", "assignment"] = (
                    "assignment" if isinstance(node.ctx, ast.Store) else "module-attribute"
                )
                expression = f"{root}." + ".".join(attributes)
                access = PrivateContractAccess(
                    path=relative,
                    module=module,
                    line=node.lineno,
                    source_module=source,
                    private_name=node.attr,
                    access_kind=kind,
                    expression=expression,
                    family=_family_from_text(f"{source} {node.attr}"),
                )
                found[(relative, node.lineno, source, node.attr, kind)] = access
            elif isinstance(node, ast.Call):
                if not (
                    isinstance(node.func, ast.Name)
                    and node.func.id == "getattr"
                    and len(node.args) >= 2
                ):
                    continue
                name_node = node.args[1]
                if not (
                    isinstance(name_node, ast.Constant)
                    and isinstance(name_node.value, str)
                    and _looks_like_private_contract(name_node.value)
                ):
                    continue
                target = node.args[0]
                source: str | None = None
                expression = "getattr(..., private)"
                if isinstance(target, ast.Name):
                    source = context.module_aliases.get(target.id)
                    expression = f"getattr({target.id}, {name_node.value!r})"
                elif isinstance(target, ast.Attribute):
                    root, attributes = _attribute_chain(target)
                    if root is not None:
                        source = _resolve_attribute_source(
                            root=root,
                            intermediate=attributes,
                            context=context,
                            contexts=contexts,
                        )
                        expression = f"getattr({root}.{'.'.join(attributes)}, {name_node.value!r})"
                if source is None or source == module:
                    continue
                access = PrivateContractAccess(
                    path=relative,
                    module=module,
                    line=node.lineno,
                    source_module=source,
                    private_name=name_node.value,
                    access_kind="getattr",
                    expression=expression,
                    family=_family_from_text(f"{source} {name_node.value}"),
                )
                found[(relative, node.lineno, source, name_node.value, "getattr")] = access
    return tuple(
        sorted(
            found.values(),
            key=lambda item: (
                item.path,
                item.line,
                item.source_module,
                item.private_name,
                item.access_kind,
            ),
        )
    )


def _strip_docstring(body: list[ast.stmt]) -> list[ast.stmt]:
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        return body[1:]
    return body


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _call_leaf(node: ast.Call) -> str:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return "<call>"


def _function_occurrence(
    path: Path,
    module: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> FunctionOccurrence | None:
    body = _strip_docstring(list(node.body))
    if not body:
        return None
    node_count = sum(1 for statement in body for _ in ast.walk(statement))
    line_span = max(1, int(getattr(node, "end_lineno", node.lineno)) - node.lineno + 1)
    if node_count < 12 or line_span < 4:
        return None

    exact_payload = {
        "async": isinstance(node, ast.AsyncFunctionDef),
        "positional": len(node.args.posonlyargs) + len(node.args.args),
        "kwonly": len(node.args.kwonlyargs),
        "vararg": node.args.vararg is not None,
        "kwarg": node.args.kwarg is not None,
        "body": [ast.dump(statement, include_attributes=False) for statement in body],
    }
    normalizer = _Normalizer()
    normalized_body = [normalizer.visit(copy.deepcopy(statement)) for statement in body]
    normalized_payload = {
        "async": isinstance(node, ast.AsyncFunctionDef),
        "positional": len(node.args.posonlyargs) + len(node.args.args),
        "kwonly": len(node.args.kwonlyargs),
        "body": [ast.dump(statement, include_attributes=False) for statement in normalized_body],
    }
    calls = tuple(
        sorted(
            {
                _call_leaf(item)
                for statement in body
                for item in ast.walk(statement)
                if isinstance(item, ast.Call)
            }
        )
    )
    attributes = tuple(
        sorted(
            {
                item.attr
                for statement in body
                for item in ast.walk(statement)
                if isinstance(item, ast.Attribute)
            }
        )
    )
    text_markers = tuple(
        sorted(
            {
                item.value.casefold()[:160]
                for statement in body
                for item in ast.walk(statement)
                if isinstance(item, ast.Constant)
                and isinstance(item.value, str)
                and item.value.strip()
            }
        )
    )
    node_types = tuple(
        type(item).__name__
        for statement in body
        for item in ast.walk(statement)
    )
    return FunctionOccurrence(
        path=path.relative_to(ROOT).as_posix(),
        module=module,
        name=node.name,
        line=node.lineno,
        end_line=int(getattr(node, "end_lineno", node.lineno)),
        exact_digest=_digest(exact_payload),
        normalized_digest=_digest(normalized_payload),
        calls=calls,
        attributes=attributes,
        text_markers=text_markers,
        node_types=node_types,
    )


def _functions(
    paths: tuple[Path, ...],
    trees: dict[str, ast.AST],
) -> tuple[FunctionOccurrence, ...]:
    result: list[FunctionOccurrence] = []
    for path in paths:
        module = _module_name(path)
        for node in ast.walk(trees[module]):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            item = _function_occurrence(path, module, node)
            if item is not None:
                result.append(item)
    return tuple(sorted(result, key=lambda item: (item.path, item.line, item.name)))


def _duplicate_kind(
    occurrences: tuple[FunctionOccurrence, ...],
    family: str,
    *,
    normalized: bool,
) -> DuplicateKind:
    paths = " ".join(item.path.casefold() for item in occurrences)
    if any(marker in paths for marker in ("generated", "compat", "legacy", "migration")):
        return "generated/compat"
    if normalized:
        return "normalized-near-duplicate"
    if family in CONTRACT_BY_FAMILY:
        return "real-duplicate"
    return "allowed-template"


def _exact_duplicate_groups(
    functions: tuple[FunctionOccurrence, ...],
) -> tuple[DuplicateGroup, ...]:
    by_digest: defaultdict[str, list[FunctionOccurrence]] = defaultdict(list)
    for item in functions:
        by_digest[item.exact_digest].append(item)
    groups: list[DuplicateGroup] = []
    for digest, raw in sorted(by_digest.items()):
        if len(raw) < 2:
            continue
        occurrences = tuple(sorted(raw, key=lambda item: (item.path, item.line)))
        family = _family_from_text(
            " ".join(f"{item.path} {item.name} {' '.join(item.calls)}" for item in occurrences)
        )
        groups.append(
            DuplicateGroup(
                digest=digest,
                kind=_duplicate_kind(occurrences, family, normalized=False),
                family=family,
                occurrences=occurrences,
                reason="exact normalized AST body",
            )
        )
    return tuple(groups)


def _normalized_duplicate_groups(
    functions: tuple[FunctionOccurrence, ...],
) -> tuple[DuplicateGroup, ...]:
    by_digest: defaultdict[str, list[FunctionOccurrence]] = defaultdict(list)
    for item in functions:
        by_digest[item.normalized_digest].append(item)
    groups: list[DuplicateGroup] = []
    for digest, raw in sorted(by_digest.items()):
        if len(raw) < 2 or len({item.exact_digest for item in raw}) < 2:
            continue
        occurrences = tuple(sorted(raw, key=lambda item: (item.path, item.line)))
        family = _family_from_text(
            " ".join(f"{item.path} {item.name} {' '.join(item.calls)}" for item in occurrences)
        )
        groups.append(
            DuplicateGroup(
                digest=digest,
                kind=_duplicate_kind(occurrences, family, normalized=True),
                family=family,
                occurrences=occurrences,
                reason="AST normalized across local names, literals and image/video media leaves",
            )
        )
    return tuple(groups)


def _semantic_families(item: FunctionOccurrence) -> set[str]:
    calls = set(item.calls)
    attributes = set(item.attributes)
    haystack = " ".join(
        (item.path, item.name, *item.calls, *item.attributes, *item.text_markers)
    ).casefold()
    families: set[str] = set()
    send_calls = {"send_document", "send_photo", "send_video"} & (calls | attributes)
    if (
        "send_document" in send_calls
        and bool({"send_photo", "send_video"} & send_calls)
    ) or (
        any(marker in haystack for marker in ("deliver", "delivery", "preview", "original"))
        and len(send_calls) >= 2
    ):
        families.add("media download/preview/original delivery")
    if "sleep" in calls and any(
        marker in haystack for marker in ("telegramapierror", "telegramnetworkerror", "retry")
    ):
        families.add("retry/backoff policies")
    if "edit_text" in calls or "edit_message_text" in calls:
        if "message is not modified" in haystack or "safe_edit" in haystack:
            families.add("safe edit/send fallback")
    if "inlinekeyboardbutton" in haystack and any(
        marker in haystack for marker in ("offset", "page", "новее", "старее", "pagination")
    ):
        families.add("pagination keyboards")
    if any(marker in haystack for marker in ("json.loads", "from_task_payload", "result_urls")):
        families.add("task payload/result mapping/formatting")
    if "auf_" in haystack and "meow_" in haystack:
        families.add("state compatibility accessors")
    if "ai_tasks" in haystack and any(marker in haystack for marker in ("select", "created_by")):
        families.add("workspace task history/ownership queries")
    if "progress" in haystack and any(
        marker in haystack for marker in ("edit_message_text", "send_message", "status_card")
    ):
        families.add("repeated progress-card updates")
    if any(marker in haystack for marker in ("model_names", "display_name", "model_alias")):
        families.add("provider/model labels")
    return families


def _semantic_duplicate_groups(
    functions: tuple[FunctionOccurrence, ...],
) -> tuple[DuplicateGroup, ...]:
    by_family: defaultdict[str, list[FunctionOccurrence]] = defaultdict(list)
    for item in functions:
        for family in _semantic_families(item):
            by_family[family].append(item)
    groups: list[DuplicateGroup] = []
    for family, raw in sorted(by_family.items()):
        if len(raw) < 2:
            continue
        occurrences = tuple(sorted(raw, key=lambda item: (item.path, item.line)))
        digest = _digest(
            {
                "family": family,
                "occurrences": [(item.module, item.name, item.line) for item in occurrences],
            }
        )
        groups.append(
            DuplicateGroup(
                digest=digest,
                kind="semantic-near-duplicate",
                family=family,
                occurrences=occurrences,
                reason="shared transport/domain signals despite different names and literals",
            )
        )
    return tuple(groups)


def _shared_contract_violations(trees: dict[str, ast.AST]) -> tuple[str, ...]:
    violations: list[str] = []
    for path in sorted(SHARED_ROOT.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = trees.get(_module_name(path)) or ast.parse(source, filename=relative)
        for node in ast.walk(tree):
            imported: tuple[str, ...] = ()
            if isinstance(node, ast.Import):
                imported = tuple(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported = (node.module or "",)
            for module in imported:
                if module.startswith(FORBIDDEN_SHARED_IMPORT_PREFIXES):
                    violations.append(f"{relative}:{node.lineno}: forbidden import {module}")
            if (
                path.name in {"editing.py", "media.py"}
                and isinstance(node, ast.ExceptHandler)
                and isinstance(node.type, ast.Name)
                and node.type.id in {"Exception", "BaseException"}
            ):
                violations.append(
                    f"{relative}:{node.lineno}: broad exception dispatch is forbidden"
                )
        if SQL_PATTERN.search(source):
            violations.append(f"{relative}: SQL/business query text is forbidden")
    return tuple(sorted(set(violations)))


def _contract_consumers(
    paths: tuple[Path, ...],
    trees: dict[str, ast.AST],
) -> dict[str, tuple[str, ...]]:
    consumers: defaultdict[str, set[str]] = defaultdict(set)
    by_symbol: defaultdict[str, list[SharedContract]] = defaultdict(list)
    for contract in CONTRACTS:
        for symbol in contract.public_symbols:
            by_symbol[symbol].append(contract)
    for path in paths:
        module = _module_name(path)
        if module.endswith(".__init__") or module.startswith("scripts"):
            continue
        tree = trees[module]
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            source = _resolve_import(module, node)
            for alias in node.names:
                for contract in by_symbol.get(alias.name, ()):  # direct symbol contract
                    target = contract.target_contract
                    target_parent = target.rsplit(".", 1)[0]
                    if source in {target, target_parent} or target.startswith(source + "."):
                        if module != target:
                            consumers[contract.family].add(module)
    return {
        family: tuple(sorted(values))
        for family, values in sorted(consumers.items())
    }


def _known_contract_output(
    private_accesses: tuple[PrivateContractAccess, ...],
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for known in KNOWN_PRIVATE_CONTRACTS:
        matches = [
            asdict(item)
            for item in private_accesses
            if item.private_name == known.private_name
            and (
                item.source_module == known.source_module
                or item.source_module.startswith(known.source_module + ".")
                or known.source_module.startswith(item.source_module + ".")
            )
        ]
        output.append(
            {
                **asdict(known),
                "status": "current-violation" if matches else "migrated",
                "current_occurrences": matches,
            }
        )
    return output


def build_inventory() -> dict[str, object]:
    paths = _python_paths()
    trees = {
        _module_name(path): ast.parse(
            path.read_text(encoding="utf-8"),
            filename=path.relative_to(ROOT).as_posix(),
        )
        for path in paths
    }
    contexts = {
        module: _collect_import_context(module, tree)
        for module, tree in trees.items()
    }
    functions = _functions(paths, trees)
    private_accesses = _private_accesses(paths, trees, contexts)
    exact_groups = _exact_duplicate_groups(functions)
    normalized_groups = _normalized_duplicate_groups(functions)
    semantic_groups = _semantic_duplicate_groups(functions)
    all_groups = (*exact_groups, *normalized_groups, *semantic_groups)
    kind_counts = Counter(group.kind for group in all_groups)
    family_counts = Counter(group.family for group in all_groups)
    consumers = _contract_consumers(paths, trees)
    contracts = []
    for contract in CONTRACTS:
        consumer_modules = consumers.get(contract.family, ())
        contracts.append(
            {
                **asdict(contract),
                "consumer_count": len(consumer_modules),
                "consumers": list(consumer_modules),
            }
        )
    return {
        "schema_version": 2,
        "production_python_files": len(paths),
        "function_count": len(functions),
        "contracts": contracts,
        "private_contract_access_count": len(private_accesses),
        "private_contract_accesses": [asdict(item) for item in private_accesses],
        "known_private_contracts": _known_contract_output(private_accesses),
        "exact_duplicate_group_count": len(exact_groups),
        "normalized_duplicate_group_count": len(normalized_groups),
        "semantic_near_duplicate_group_count": len(semantic_groups),
        "duplicate_kind_counts": dict(sorted(kind_counts.items())),
        "duplicate_family_counts": dict(sorted(family_counts.items())),
        "exact_duplicate_groups": [asdict(group) for group in exact_groups],
        "normalized_duplicate_groups": [asdict(group) for group in normalized_groups],
        "semantic_near_duplicate_groups": [asdict(group) for group in semantic_groups],
        "shared_contract_violations": list(_shared_contract_violations(trees)),
    }


def validate_inventory(data: dict[str, object]) -> list[str]:
    errors: list[str] = []
    contracts = list(data["contracts"])
    families = {str(item["family"]) for item in contracts}
    expected_families = {item.family for item in CONTRACTS}
    missing_families = sorted(expected_families - families)
    if missing_families:
        errors.append("missing contract families: " + ", ".join(missing_families))
    for item in contracts:
        target = str(item["target_contract"])
        if any(marker in target for marker in TEMPORARY_TARGET_MARKERS):
            errors.append(
                f"temporary installer/hotfix cannot be canonical target: {item['family']} -> {target}"
            )
        if not item["current_owner"] or not item["retirement_issue"]:
            errors.append(f"incomplete ownership contract: {item['family']}")
        if item["status"] == "canonical" and int(item["consumer_count"]) < 2:
            errors.append(
                f"canonical public contract has fewer than two production consumers: {item['family']}"
            )
    private_accesses = list(data["private_contract_accesses"])
    if private_accesses:
        rendered = ", ".join(
            f"{item['path']}:{item['line']} {item['expression']}"
            for item in private_accesses[:30]
        )
        suffix = "" if len(private_accesses) <= 30 else f" (+{len(private_accesses) - 30} more)"
        errors.append("private cross-module helper contracts: " + rendered + suffix)
    shared_violations = list(data["shared_contract_violations"])
    if shared_violations:
        errors.append("shared helper boundary violations: " + "; ".join(shared_violations))
    known_names = {str(item["private_name"]) for item in data["known_private_contracts"]}
    required_known = {
        "_task_line",
        "_load_user_tasks",
        "_task_list_keyboard",
        "_MODEL_NAMES",
        "_edit_or_answer",
        "_validated_model",
        "_reference_from_data",
    }
    if not required_known.issubset(known_names):
        errors.append(
            "known private contract registry is incomplete: "
            + ", ".join(sorted(required_known - known_names))
        )
    semantic_groups = list(data["semantic_near_duplicate_groups"])
    if not any(
        group["family"] == "media download/preview/original delivery"
        and len(group["occurrences"]) >= 2
        for group in semantic_groups
    ):
        errors.append("image/video delivery near-duplicates are missing from semantic inventory")
    valid_kinds = {
        "real-duplicate",
        "normalized-near-duplicate",
        "semantic-near-duplicate",
        "generated/compat",
        "allowed-template",
    }
    for key in (
        "exact_duplicate_groups",
        "normalized_duplicate_groups",
        "semantic_near_duplicate_groups",
    ):
        for group in data[key]:
            if group["kind"] not in valid_kinds:
                errors.append(f"unclassified duplicate group: {group['digest']}")
    return errors


def render_markdown(data: dict[str, object]) -> str:
    lines = [
        "# Shared contract inventory",
        "",
        f"- Production Python files: **{data['production_python_files']}**",
        f"- Functions inventoried: **{data['function_count']}**",
        f"- Private cross-module contracts: **{data['private_contract_access_count']}**",
        f"- Exact duplicate groups: **{data['exact_duplicate_group_count']}**",
        f"- Normalized near-duplicate groups: **{data['normalized_duplicate_group_count']}**",
        f"- Semantic near-duplicate groups: **{data['semantic_near_duplicate_group_count']}**",
        "",
        "## Contract ownership",
        "",
        "| Family | Current owner | Target | Retirement | Status | Consumers |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for item in data["contracts"]:
        lines.append(
            "| {family} | `{current_owner}` | `{target_contract}` | {retirement_issue} | "
            "{status} | {consumer_count} |".format(**item)
        )
    lines.extend(["", "## Known private contracts", ""])
    for item in data["known_private_contracts"]:
        lines.append(
            f"- `{item['source_module']}.{item['private_name']}` → "
            f"`{item['public_name']}`: **{item['status']}**, retirement {item['retirement_issue']}."
        )
    lines.extend(["", "## Current private accesses", ""])
    accesses = list(data["private_contract_accesses"])
    if not accesses:
        lines.append("No current private cross-module helper accesses.")
    else:
        for item in accesses:
            lines.append(
                f"- `{item['path']}:{item['line']}` `{item['expression']}` "
                f"({item['access_kind']}, {item['family']})."
            )
    lines.extend(["", "## Semantic near-duplicate families", ""])
    for group in data["semantic_near_duplicate_groups"]:
        lines.append(
            f"- **{group['family']}**: {len(group['occurrences'])} functions; {group['reason']}."
        )
    lines.append("")
    return "\n".join(lines)


def _print_summary(data: dict[str, object]) -> None:
    print(f"Production Python files: {data['production_python_files']}")
    print(f"Functions inventoried: {data['function_count']}")
    print(f"Private helper contracts: {data['private_contract_access_count']}")
    print(f"Exact duplicate groups: {data['exact_duplicate_group_count']}")
    print(f"Normalized near-duplicate groups: {data['normalized_duplicate_group_count']}")
    print(f"Semantic near-duplicate groups: {data['semantic_near_duplicate_group_count']}")
    for kind, count in dict(data["duplicate_kind_counts"]).items():
        print(f"- {kind}: {count}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inventory package-wide shared contracts")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-json", type=Path)
    parser.add_argument("--write-markdown", type=Path)
    args = parser.parse_args(argv)

    data = build_inventory()
    if args.write_json is not None:
        output = args.write_json if args.write_json.is_absolute() else ROOT / args.write_json
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.write_markdown is not None:
        output = (
            args.write_markdown
            if args.write_markdown.is_absolute()
            else ROOT / args.write_markdown
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_markdown(data), encoding="utf-8")
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
