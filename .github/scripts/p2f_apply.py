from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parents[2]
inv_path = root / "docs/p2_stability_inventory.json"
data = json.loads(inv_path.read_text(encoding="utf-8"))
for item in data["broad_exceptions"]:
    if item["path"] == "velvet_bot/ai_job_runtime.py" and item["function"] == "create":
        item["classification"] = "approved_boundary"
        item["reason"] = "compensate-created-ai-job"

approved = [item for item in data["broad_exceptions"] if item["classification"] == "approved_boundary"]
unresolved = [item for item in data["broad_exceptions"] if item["classification"] == "unresolved"]
data.update(
    schema_version=8,
    generated_from_commit="p2f-ai-job-tracker-boundary",
    broad_exception_approved=len(approved),
    broad_exception_unresolved=len(unresolved),
    broad_exception_unresolved_files=len({item["path"] for item in unresolved}),
    next_slice={"target": "velvet_bot/app/bootstrap.py", "kind": "broad_exception_triage"},
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
for path, count in by_file.most_common():
    lines.append(f"- `{path}`: {count}.")
lines += [
    "", "## Risky callbacks", "",
    "- Нет. Callback late/missing baseline закрыт.", "",
    "## Следующий срез", "",
    "- `velvet_bot/app/bootstrap.py`: broad-exception triage shutdown/startup boundaries.", "",
    "## Правило обновления", "",
    "Approved boundary требует inline-маркер и отдельный поведенческий тест. Raw count не уменьшается от классификации; unresolved count отражает оставшийся долг.", "",
]
(root / "docs/p2_stability_inventory.md").write_text("\n".join(lines), encoding="utf-8")

old = "3. P2E: AI worker boundaries классифицированы; unresolved broad baseline 67 → 64."
new = "3. P2F: AI job tracker compensation boundary классифицирован; unresolved broad baseline 64 → 63."
for name in ("development_status.md", "project_memory.md"):
    path = root / "docs" / name
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(name)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

changelog = root / "CHANGELOG.md"
text = changelog.read_text(encoding="utf-8")
entry = "\n### P2F: AI job tracker boundary\n\n- Классифицирована компенсационная граница создания status message для AI job.\n- Unresolved broad baseline уменьшен с 64 до 63.\n"
if entry.strip() not in text:
    text = text.replace("## [Unreleased]\n", "## [Unreleased]\n" + entry, 1)
changelog.write_text(text, encoding="utf-8")
