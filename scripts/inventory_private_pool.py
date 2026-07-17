from __future__ import annotations

import argparse
import ast
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOT = ROOT / "velvet_bot"
_DATABASE_PATH = "velvet_bot/database.py"
_PRIVATE_NAME = "_require_pool"


@dataclass(frozen=True, slots=True)
class PrivatePoolFinding:
    path: str
    line: int
    column: int
    access_kind: str
    class_name: str | None
    function_name: str | None
    allowed_internal: bool

    @property
    def scope(self) -> str:
        parts = [part for part in (self.class_name, self.function_name) if part]
        return ".".join(parts) or "<module>"


class _PrivatePoolVisitor(ast.NodeVisitor):
    def __init__(self, *, relative_path: str) -> None:
        self.relative_path = relative_path
        self.class_stack: list[str] = []
        self.function_stack: list[str] = []
        self.findings: list[PrivatePoolFinding] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.function_stack.append(node.name)
        self.generic_visit(node)
        self.function_stack.pop()

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr == _PRIVATE_NAME:
            self._record(node, access_kind="attribute")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == _PRIVATE_NAME
        ):
            self._record(node, access_kind="dynamic_getattr")
        self.generic_visit(node)

    def _record(self, node: ast.AST, *, access_kind: str) -> None:
        class_name = self.class_stack[-1] if self.class_stack else None
        function_name = self.function_stack[-1] if self.function_stack else None
        self.findings.append(
            PrivatePoolFinding(
                path=self.relative_path,
                line=int(getattr(node, "lineno", 0)),
                column=int(getattr(node, "col_offset", 0)),
                access_kind=access_kind,
                class_name=class_name,
                function_name=function_name,
                allowed_internal=(
                    self.relative_path == _DATABASE_PATH
                    and class_name == "Database"
                ),
            )
        )


def collect_findings(root: Path = ROOT) -> tuple[PrivatePoolFinding, ...]:
    production_root = root / "velvet_bot"
    findings: list[PrivatePoolFinding] = []
    for path in sorted(production_root.rglob("*.py")):
        relative_path = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=relative_path)
        visitor = _PrivatePoolVisitor(relative_path=relative_path)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return tuple(
        sorted(
            findings,
            key=lambda item: (item.path, item.line, item.column, item.access_kind),
        )
    )


def external_findings(
    findings: Iterable[PrivatePoolFinding],
) -> tuple[PrivatePoolFinding, ...]:
    return tuple(item for item in findings if not item.allowed_internal)


def format_findings(findings: Iterable[PrivatePoolFinding]) -> str:
    items = tuple(findings)
    if not items:
        return "Внешние обращения к Database._require_pool() не найдены."
    lines = ["Найдены внешние обращения к Database._require_pool():"]
    for item in items:
        lines.append(
            f"- {item.path}:{item.line}:{item.column + 1} "
            f"[{item.access_kind}] {item.scope}"
        )
    return "\n".join(lines)


def _json_payload(findings: Iterable[PrivatePoolFinding]) -> str:
    return json.dumps(
        [asdict(item) | {"scope": item.scope} for item in findings],
        ensure_ascii=False,
        indent=2,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Инвентаризация обращений к приватному Database._require_pool()",
    )
    parser.add_argument("--json", action="store_true", help="Вывести JSON")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Показать также допустимые внутренние обращения класса Database",
    )
    parser.add_argument(
        "--fail-on-external",
        action="store_true",
        help="Вернуть код 1, если найдены внешние production-обращения",
    )
    args = parser.parse_args(argv)

    findings = collect_findings()
    selected = findings if args.all else external_findings(findings)
    print(_json_payload(selected) if args.json else format_findings(selected))
    if args.fail_on_external and external_findings(findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
