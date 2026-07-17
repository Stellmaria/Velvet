from __future__ import annotations

import argparse
import ast
import hashlib
import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_ROOT = ROOT / "velvet_bot"
DEFAULT_BASELINE = ROOT / "docs" / "private_pool_inventory.json"
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

    @property
    def identity(self) -> str:
        return f"{self.access_kind}|{self.scope}"


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


def summarize_external(
    findings: Iterable[PrivatePoolFinding],
) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[PrivatePoolFinding]] = defaultdict(list)
    for item in external_findings(findings):
        grouped[item.path].append(item)

    summary: dict[str, dict[str, object]] = {}
    for path, items in sorted(grouped.items()):
        identities = sorted(item.identity for item in items)
        identity_payload = "\n".join(identities) + "\n"
        summary[path] = {
            "count": len(items),
            "identity_sha256": hashlib.sha256(
                identity_payload.encode("utf-8")
            ).hexdigest(),
        }
    return summary


def load_baseline(path: Path = DEFAULT_BASELINE) -> Mapping[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError(f"Неподдерживаемая версия baseline: {payload.get('schema_version')!r}")
    return payload


def compare_with_baseline(
    findings: Iterable[PrivatePoolFinding],
    baseline: Mapping[str, object],
) -> tuple[str, ...]:
    current = summarize_external(findings)
    raw_files = baseline.get("files")
    if not isinstance(raw_files, list):
        return ("Baseline не содержит список files.",)

    expected: dict[str, dict[str, object]] = {}
    for record in raw_files:
        if not isinstance(record, dict) or not isinstance(record.get("path"), str):
            return ("Baseline содержит некорректную запись files.",)
        expected[str(record["path"])] = record

    errors: list[str] = []
    for path in sorted(set(current) - set(expected)):
        errors.append(f"Новое внешнее обращение вне baseline: {path}")
    for path in sorted(set(expected) - set(current)):
        errors.append(
            f"Baseline устарел: обращения удалены из {path}; обновите inventory после отдельного среза."
        )
    for path in sorted(set(current) & set(expected)):
        current_record = current[path]
        expected_record = expected[path]
        expected_count = int(expected_record.get("count", -1))
        expected_digest = str(expected_record.get("identity_sha256", ""))
        if current_record["count"] != expected_count:
            errors.append(
                f"Изменилось число обращений {path}: "
                f"ожидалось {expected_count}, найдено {current_record['count']}"
            )
        if current_record["identity_sha256"] != expected_digest:
            errors.append(
                f"Изменился набор методов с private pool access: {path}"
            )

    expected_total = int(baseline.get("total_external_findings", -1))
    current_total = sum(int(record["count"]) for record in current.values())
    if current_total != expected_total:
        errors.append(
            f"Изменилось общее число обращений: ожидалось {expected_total}, найдено {current_total}"
        )
    expected_files = int(baseline.get("total_files", -1))
    if len(current) != expected_files:
        errors.append(
            f"Изменилось число production-файлов: ожидалось {expected_files}, найдено {len(current)}"
        )
    return tuple(errors)


def format_baseline_errors(errors: Iterable[str]) -> str:
    items = tuple(errors)
    if not items:
        return "Private pool baseline соответствует production-коду."
    return "Private pool baseline нарушен:\n" + "\n".join(
        f"- {item}" for item in items
    )


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
    parser.add_argument(
        "--check-baseline",
        action="store_true",
        help="Сравнить production-код с docs/private_pool_inventory.json",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="Путь к inventory baseline",
    )
    args = parser.parse_args(argv)

    findings = collect_findings()
    selected = findings if args.all else external_findings(findings)
    print(_json_payload(selected) if args.json else format_findings(selected))

    if args.check_baseline:
        errors = compare_with_baseline(findings, load_baseline(args.baseline))
        print(format_baseline_errors(errors))
        if errors:
            return 1
    if args.fail_on_external and external_findings(findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
