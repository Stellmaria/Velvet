from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[2]
path = root / "velvet_bot/backup_runtime.py"
text = path.read_text(encoding="utf-8")
old = '''        except Exception:
            final_path.unlink(missing_ok=True)
            self._manifest_path(final_path).unlink(missing_ok=True)
            raise
'''
new = '''        except asyncio.CancelledError:
            final_path.unlink(missing_ok=True)
            self._manifest_path(final_path).unlink(missing_ok=True)
            raise
        except Exception:  # p2-approved-boundary: cleanup-invalid-backup-artifacts
            final_path.unlink(missing_ok=True)
            self._manifest_path(final_path).unlink(missing_ok=True)
            raise
'''
if old not in text:
    raise SystemExit("backup cleanup block")
path.write_text(text.replace(old, new, 1), encoding="utf-8")


def broad(node: ast.ExceptHandler) -> bool:
    value = node.type
    if isinstance(value, ast.Name):
        return value.id == "Exception"
    if isinstance(value, ast.Tuple):
        return any(isinstance(item, ast.Name) and item.id == "Exception" for item in value.elts)
    return False

entries = []
for source_path in sorted((root / "velvet_bot").rglob("*.py")):
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
                entries.append({
                    "path": relative,
                    "function": ".".join(parents) or "<module>",
                    "line": node.lineno,
                    "handler_module": "/handlers/" in f"/{relative}",
                    "classification": "approved_boundary" if reason else "unresolved",
                    "reason": reason,
                })
            self.generic_visit(node)

    Visitor().visit(tree)
entries.sort(key=lambda item: (item["path"], item["line"]))
inv_path = root / "docs/p2_stability_inventory.json"
data = json.loads(inv_path.read_text(encoding="utf-8"))
data["broad_exceptions"] = entries
approved = [item for item in entries if item["classification"] == "approved_boundary"]
unresolved = [item for item in entries if item["classification"] == "unresolved"]
data.update(
    schema_version=12,
    generated_from_commit="p2j-backup-runtime-cleanup",
    broad_exception_total=len(entries),
    broad_exception_files=len({item["path"] for item in entries}),
    broad_exception_approved=len(approved),
    broad_exception_unresolved=len(unresolved),
    broad_exception_unresolved_files=len({item["path"] for item in unresolved}),
    next_slice={"target": "velvet_bot/backup_service.py", "kind": "broad_exception_triage"},
)
inv_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

by_file = Counter(item["path"] for item in unresolved)
lines = ["# P2 stability inventory", "", "## Сводка", "",
         f"- raw: **{len(entries)}** / **{data['broad_exception_files']}** files;",
         f"- approved: **{len(approved)}**;",
         f"- unresolved: **{len(unresolved)}** / **{len(by_file)}** files;",
         f"- risky callbacks: **{data['risky_callback_total']}**.", "",
         "## Approved broad boundaries", ""]
for item in approved:
    lines.append(f"- `{item['path']}:{item['line']}` `{item['function']}`: {item['reason']}.")
lines += ["", "## Unresolved broad exceptions by file", ""]
for name, count in by_file.most_common():
    lines.append(f"- `{name}`: {count}.")
lines += ["", "## Следующий срез", "", "- `velvet_bot/backup_service.py`.", ""]
(root / "docs/p2_stability_inventory.md").write_text("\n".join(lines), encoding="utf-8")

old = "3. P2I: Telegram audit sink boundary классифицирован; unresolved broad baseline 56 → 55."
new = "3. P2J: backup runtime cleanup boundary усилен; unresolved broad baseline 55 → 54."
for name in ("development_status.md", "project_memory.md"):
    doc = root / "docs" / name
    value = doc.read_text(encoding="utf-8")
    if old not in value:
        raise SystemExit(name)
    doc.write_text(value.replace(old, new, 1), encoding="utf-8")

changelog = root / "CHANGELOG.md"
value = changelog.read_text(encoding="utf-8")
entry = "\n### P2J: backup runtime cleanup\n\n- Cancellation теперь удаляет созданные backup artifacts.\n- Unresolved broad baseline уменьшен с 55 до 54.\n"
if entry.strip() not in value:
    value = value.replace("## [Unreleased]\n", "## [Unreleased]\n" + entry, 1)
changelog.write_text(value, encoding="utf-8")
