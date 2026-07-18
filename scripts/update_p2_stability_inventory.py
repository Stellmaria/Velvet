from __future__ import annotations

import argparse
import ast
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "velvet_bot"
INVENTORY_PATH = ROOT / "docs/p2_stability_inventory.json"
MARKDOWN_PATH = ROOT / "docs/p2_stability_inventory.md"
MARKER = "p2-approved-boundary:"


def _dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    if isinstance(node, ast.Call):
        return _dotted(node.func)
    return ""


def _is_broad(handler: ast.ExceptHandler) -> bool:
    value = handler.type
    if isinstance(value, ast.Name):
        return value.id == "Exception"
    if isinstance(value, ast.Tuple):
        return any(
            isinstance(item, ast.Name) and item.id == "Exception"
            for item in value.elts
        )
    return False


def _is_callback(node: ast.AsyncFunctionDef) -> bool:
    return any("callback_query" in _dotted(item) for item in node.decorator_list)


def _is_acknowledgement(node: ast.Await) -> bool:
    name = _dotted(node.value)
    leaf = name.rsplit(".", 1)[-1].casefold()
    return name.endswith("callback.answer") or (
        "callback" in leaf and ("answer" in leaf or "acknowledge" in leaf)
    )


def _passes_callback(node: ast.Await) -> bool:
    if not isinstance(node.value, ast.Call):
        return False
    values = [*node.value.args, *(item.value for item in node.value.keywords)]
    return any(isinstance(item, ast.Name) and item.id == "callback" for item in values)


def build_inventory(*, generated_from: str, schema_version: int) -> dict[str, Any]:
    broad_entries: list[dict[str, Any]] = []
    callbacks: list[dict[str, Any]] = []

    for path in sorted(PACKAGE.rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8")
        source_lines = source.splitlines()
        tree = ast.parse(source, filename=relative)
        parents: list[str] = []

        class Visitor(ast.NodeVisitor):
            def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
                parents.append(node.name)
                self.generic_visit(node)
                parents.pop()

            def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
                function = ".".join([*parents, node.name])
                if _is_callback(node):
                    awaits = sorted(
                        (
                            item
                            for item in ast.walk(node)
                            if isinstance(item, ast.Await)
                        ),
                        key=lambda item: (item.lineno, item.col_offset),
                    )
                    ack = next(
                        (item for item in awaits if _is_acknowledgement(item)),
                        None,
                    )
                    before = [
                        item
                        for item in awaits
                        if ack is None or item.lineno < ack.lineno
                    ]
                    delegated = (
                        ack is None
                        and len(awaits) == 1
                        and _passes_callback(awaits[0])
                    )
                    if delegated:
                        risk = "delegated"
                    elif ack is None:
                        risk = "missing_ack"
                    elif not before:
                        risk = "early_ack"
                    elif len(before) == 1:
                        risk = "guarded_ack"
                    else:
                        risk = "late_ack"
                    callbacks.append(
                        {
                            "path": relative,
                            "function": function,
                            "line": node.lineno,
                            "ack_line": ack.lineno if ack else None,
                            "pre_ack_awaits": len(before),
                            "total_awaits": len(awaits),
                            "risk": risk,
                        }
                    )
                parents.append(node.name)
                self.generic_visit(node)
                parents.pop()

            def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
                if _is_broad(node):
                    line = source_lines[node.lineno - 1]
                    reason = line.split(MARKER, 1)[1].strip() if MARKER in line else None
                    broad_entries.append(
                        {
                            "path": relative,
                            "function": ".".join(parents) or "<module>",
                            "line": node.lineno,
                            "handler_module": "/handlers/" in f"/{relative}",
                            "classification": (
                                "approved_boundary" if reason else "unresolved"
                            ),
                            "reason": reason,
                        }
                    )
                self.generic_visit(node)

        Visitor().visit(tree)

    broad_entries.sort(key=lambda item: (item["path"], item["line"]))
    callbacks.sort(key=lambda item: (item["path"], item["line"]))
    approved = [
        item for item in broad_entries
        if item["classification"] == "approved_boundary"
    ]
    unresolved = [
        item for item in broad_entries if item["classification"] == "unresolved"
    ]
    risky = [
        item for item in callbacks
        if item["risk"] in {"missing_ack", "late_ack"}
    ]
    guarded = [item for item in callbacks if item["risk"] == "guarded_ack"]
    delegated = [item for item in callbacks if item["risk"] == "delegated"]

    return {
        "schema_version": schema_version,
        "generated_from_commit": generated_from,
        "broad_exception_total": len(broad_entries),
        "broad_exception_files": len({item["path"] for item in broad_entries}),
        "broad_exception_approved": len(approved),
        "broad_exception_unresolved": len(unresolved),
        "broad_exception_unresolved_files": len({item["path"] for item in unresolved}),
        "callback_total": len(callbacks),
        "risky_callback_total": len(risky),
        "risky_callback_files": len({item["path"] for item in risky}),
        "guarded_callback_total": len(guarded),
        "delegated_callback_total": len(delegated),
        "next_slice": (
            {"target": unresolved[0]["path"], "kind": "broad_exception_triage"}
            if unresolved
            else None
        ),
        "broad_exceptions": broad_entries,
        "callbacks": callbacks,
    }


def render_markdown(data: dict[str, Any]) -> str:
    approved = [
        item for item in data["broad_exceptions"]
        if item["classification"] == "approved_boundary"
    ]
    unresolved = [
        item for item in data["broad_exceptions"]
        if item["classification"] == "unresolved"
    ]
    unresolved_by_file = Counter(item["path"] for item in unresolved)
    lines = [
        "# P2 stability inventory",
        "",
        "AST-инвентаризация широких исключений и callback acknowledgment.",
        "",
        "## Сводка",
        "",
        f"- raw broad exceptions: **{data['broad_exception_total']}** в **{data['broad_exception_files']}** файлах;",
        f"- approved boundaries: **{data['broad_exception_approved']}**;",
        f"- unresolved broad exceptions: **{data['broad_exception_unresolved']}** в **{data['broad_exception_unresolved_files']}** файлах;",
        f"- callback handlers: **{data['callback_total']}**;",
        f"- late/missing callbacks: **{data['risky_callback_total']}**;",
        f"- guarded callbacks: **{data['guarded_callback_total']}**;",
        f"- delegated callbacks: **{data['delegated_callback_total']}**.",
        "",
        "## Approved broad boundaries",
        "",
    ]
    for item in approved:
        lines.append(
            f"- `{item['path']}:{item['line']}` `{item['function']}`: {item['reason']}."
        )
    lines.extend(["", "## Unresolved broad exceptions by file", ""])
    for path, count in unresolved_by_file.most_common():
        lines.append(f"- `{path}`: {count}.")
    lines.extend(["", "## Следующий срез", ""])
    next_slice = data["next_slice"]
    lines.append(f"- `{next_slice['target']}`." if next_slice else "- Нет.")
    lines.extend(
        [
            "",
            "## Правило обновления",
            "",
            "Запустите `python scripts/update_p2_stability_inventory.py --label <phase> --schema-version <n>` после изменения broad catches или callback acknowledgment.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--schema-version", type=int, required=True)
    args = parser.parse_args()
    data = build_inventory(
        generated_from=args.label,
        schema_version=args.schema_version,
    )
    INVENTORY_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MARKDOWN_PATH.write_text(render_markdown(data), encoding="utf-8")


if __name__ == "__main__":
    main()
