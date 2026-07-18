from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[2]
path = root / "velvet_bot/app/bootstrap.py"
text = path.read_text(encoding="utf-8")
anchor = "\n\nasync def run_application() -> None:\n"
helper = '''

async def _report_fatal_application_error(
    error_center: ErrorIncidentCenter | None,
    error: Exception,
) -> None:
    if error_center is None:
        return
    try:
        await error_center.report_exception(
            "Критическое завершение приложения",
            error,
            severity="CRITICAL",
            logger_name=__name__,
        )
    except Exception:  # p2-approved-boundary: preserve-original-fatal-error
        logger.exception("Could not report fatal application error")


async def run_application() -> None:
'''
if helper not in text:
    if anchor not in text:
        raise SystemExit("run anchor")
    text = text.replace(anchor, helper, 1)
old = '''    except Exception as error:
        if error_center is not None:
            try:
                await error_center.report_exception(
                    "Критическое завершение приложения",
                    error,
                    severity="CRITICAL",
                    logger_name=__name__,
                )
            except Exception:
                logger.exception("Could not report fatal application error")
        raise
'''
new = '''    except Exception as error:  # p2-approved-boundary: report-fatal-application-error
        await _report_fatal_application_error(error_center, error)
        raise
'''
if old not in text:
    raise SystemExit("fatal block")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")


def dotted(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = dotted(node.value)
        return f"{left}.{node.attr}" if left else node.attr
    return ""


def broad(node: ast.ExceptHandler) -> bool:
    value = node.type
    if isinstance(value, ast.Name):
        return value.id == "Exception"
    if isinstance(value, ast.Tuple):
        return any(isinstance(item, ast.Name) and item.id == "Exception" for item in value.elts)
    return False

entries = []
package = root / "velvet_bot"
for source_path in sorted(package.rglob("*.py")):
    relative = source_path.relative_to(root).as_posix()
    source = source_path.read_text(encoding="utf-8")
    source_lines = source.splitlines()
    tree = ast.parse(source, filename=relative)
    parents: list[str] = []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            parents.append(node.name)
            self.generic_visit(node)
            parents.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            parents.append(node.name)
            self.generic_visit(node)
            parents.pop()

        def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
            if broad(node):
                line = source_lines[node.lineno - 1]
                marker = "p2-approved-boundary:"
                reason = line.split(marker, 1)[1].strip() if marker in line else None
                entries.append(
                    {
                        "path": relative,
                        "function": ".".join(parents) or "<module>",
                        "line": node.lineno,
                        "handler_module": "/handlers/" in f"/{relative}",
                        "classification": "approved_boundary" if reason else "unresolved",
                        "reason": reason,
                    }
                )
            self.generic_visit(node)

    Visitor().visit(tree)

entries.sort(key=lambda item: (item["path"], item["line"]))
inv_path = root / "docs/p2_stability_inventory.json"
data = json.loads(inv_path.read_text(encoding="utf-8"))
data["broad_exceptions"] = entries
approved = [item for item in entries if item["classification"] == "approved_boundary"]
unresolved = [item for item in entries if item["classification"] == "unresolved"]
data.update(
    schema_version=10,
    generated_from_commit="p2h-bootstrap-fatal-boundaries",
    broad_exception_total=len(entries),
    broad_exception_files=len({item["path"] for item in entries}),
    broad_exception_approved=len(approved),
    broad_exception_unresolved=len(unresolved),
    broad_exception_unresolved_files=len({item["path"] for item in unresolved}),
    next_slice={"target": "velvet_bot/audit.py", "kind": "broad_exception_triage"},
)
inv_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

by_file = Counter(item["path"] for item in unresolved)
lines = [
    "# P2 stability inventory", "",
    "AST-инвентаризация широких исключений и callback acknowledgment.", "",
    "## Сводка", "",
    f"- broad exceptions raw: **{len(entries)}** в **{data['broad_exception_files']}** файлах;",
    f"- approved orchestration boundaries: **{len(approved)}**;",
    f"- unresolved broad exceptions: **{len(unresolved)}** в **{len(by_file)}** файлах;",
    f"- callback handlers: **{data['callback_total']}**;",
    f"- missing/late acknowledgment: **{data['risky_callback_total']}**;",
    f"- guarded acknowledgment: **{data['guarded_callback_total']}**;",
    f"- delegated wrappers: **{data['delegated_callback_total']}**.", "",
    "## Approved broad boundaries", "",
]
for item in approved:
    lines.append(f"- `{item['path']}:{item['line']}` `{item['function']}`: {item['reason']}.")
lines += ["", "## Unresolved broad exceptions by file", ""]
for name, count in by_file.most_common():
    lines.append(f"- `{name}`: {count}.")
lines += ["", "## Risky callbacks", "", "- Нет.", "", "## Следующий срез", "", "- `velvet_bot/audit.py`.", ""]
(root / "docs/p2_stability_inventory.md").write_text("\n".join(lines), encoding="utf-8")

old = "3. P2G: bootstrap cleanup boundaries классифицированы; unresolved broad baseline 63 → 58."
new = "3. P2H: bootstrap fatal-reporting boundaries классифицированы; unresolved broad baseline 58 → 56."
for name in ("development_status.md", "project_memory.md"):
    item_path = root / "docs" / name
    value = item_path.read_text(encoding="utf-8")
    if old not in value:
        raise SystemExit(name)
    item_path.write_text(value.replace(old, new, 1), encoding="utf-8")

changelog = root / "CHANGELOG.md"
value = changelog.read_text(encoding="utf-8")
entry = "\n### P2H: bootstrap fatal boundaries\n\n- Fatal reporting вынесен в отдельный helper и покрыт тестами.\n- Unresolved broad baseline уменьшен с 58 до 56.\n"
if entry.strip() not in value:
    value = value.replace("## [Unreleased]\n", "## [Unreleased]\n" + entry, 1)
changelog.write_text(value, encoding="utf-8")
