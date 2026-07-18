from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[2]
inv_path = root / "docs/p2_stability_inventory.json"
data = json.loads(inv_path.read_text(encoding="utf-8"))
for item in data["broad_exceptions"]:
    if item["path"] == "velvet_bot/audit.py" and item["function"] == "send":
        item["classification"] = "approved_boundary"
        item["reason"] = "isolate-telegram-audit-sink"

approved = [item for item in data["broad_exceptions"] if item["classification"] == "approved_boundary"]
unresolved = [item for item in data["broad_exceptions"] if item["classification"] == "unresolved"]
data.update(
    schema_version=11,
    generated_from_commit="p2i-audit-sink-boundary",
    broad_exception_approved=len(approved),
    broad_exception_unresolved=len(unresolved),
    broad_exception_unresolved_files=len({item["path"] for item in unresolved}),
    next_slice={"target": "velvet_bot/backup_runtime.py", "kind": "broad_exception_triage"},
)
inv_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

by_file = Counter(item["path"] for item in unresolved)
lines = [
    "# P2 stability inventory", "",
    "AST-инвентаризация широких исключений и callback acknowledgment.", "",
    "## Сводка", "",
    f"- broad exceptions raw: **{data['broad_exception_total']}** в **{data['broad_exception_files']}** файлах;",
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
lines += ["", "## Risky callbacks", "", "- Нет.", "", "## Следующий срез", "", "- `velvet_bot/backup_runtime.py`.", ""]
(root / "docs/p2_stability_inventory.md").write_text("\n".join(lines), encoding="utf-8")

old = "3. P2H: bootstrap fatal-reporting boundaries классифицированы; unresolved broad baseline 58 → 56."
new = "3. P2I: Telegram audit sink boundary классифицирован; unresolved broad baseline 56 → 55."
for name in ("development_status.md", "project_memory.md"):
    path = root / "docs" / name
    value = path.read_text(encoding="utf-8")
    if old not in value:
        raise SystemExit(name)
    path.write_text(value.replace(old, new, 1), encoding="utf-8")

changelog = root / "CHANGELOG.md"
value = changelog.read_text(encoding="utf-8")
entry = "\n### P2I: audit sink boundary\n\n- Классифицирован best-effort Telegram audit sink.\n- Unresolved broad baseline уменьшен с 56 до 55.\n"
if entry.strip() not in value:
    value = value.replace("## [Unreleased]\n", "## [Unreleased]\n" + entry, 1)
changelog.write_text(value, encoding="utf-8")
