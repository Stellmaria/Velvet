from __future__ import annotations

import ast
import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[2]
path = root / "velvet_bot/backup_service.py"
text = path.read_text(encoding="utf-8")
old = '''            except Exception as error:
                await self._fail_run(database, run_id=run_id, error=error)
                raise
'''
new = '''            except asyncio.CancelledError as error:
                await self._fail_run(database, run_id=run_id, error=error)
                raise
            except Exception as error:  # p2-approved-boundary: compensate-running-backup
                await self._fail_run(database, run_id=run_id, error=error)
                raise
'''
if old not in text:
    raise SystemExit("create backup catch")
text = text.replace(old, new, 1)
old_worker = '''        except Exception:
            logger.exception("Scheduled backup worker failed")
'''
new_worker = '''        except Exception:  # p2-approved-boundary: isolate-backup-worker-iteration
            logger.exception("Scheduled backup worker failed")
'''
if old_worker not in text:
    raise SystemExit("worker catch")
path.write_text(text.replace(old_worker, new_worker, 1), encoding="utf-8")


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
    schema_version=13,
    generated_from_commit="p2k-backup-service-boundaries",
    broad_exception_total=len(entries),
    broad_exception_files=len({item["path"] for item in entries}),
    broad_exception_approved=len(approved),
    broad_exception_unresolved=len(unresolved),
    broad_exception_unresolved_files=len({item["path"] for item in unresolved}),
    next_slice={"target": "velvet_bot/calibrated_ai_quality.py", "kind": "next_unresolved_after_ast_scan"},
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
lines += ["", "## Следующий срез", "", "- первый unresolved entry из актуального AST inventory.", ""]
(root / "docs/p2_stability_inventory.md").write_text("\n".join(lines), encoding="utf-8")

old = "3. P2J: backup runtime cleanup boundary усилен; unresolved broad baseline 55 → 54."
new = "3. P2K: backup service compensation и worker isolation усилены; unresolved broad baseline 54 → 52."
for name in ("development_status.md", "project_memory.md"):
    doc = root / "docs" / name
    value = doc.read_text(encoding="utf-8")
    if old not in value:
        raise SystemExit(name)
    doc.write_text(value.replace(old, new, 1), encoding="utf-8")

changelog = root / "CHANGELOG.md"
value = changelog.read_text(encoding="utf-8")
entry = "\n### P2K: backup service boundaries\n\n- Cancellation теперь завершает running backup как failed.\n- Worker iteration boundary классифицирован.\n- Unresolved broad baseline уменьшен с 54 до 52.\n"
if entry.strip() not in value:
    value = value.replace("## [Unreleased]\n", "## [Unreleased]\n" + entry, 1)
changelog.write_text(value, encoding="utf-8")
