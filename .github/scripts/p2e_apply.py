from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "velvet_bot/ai_quality.py": ("process_once", "compensate-claimed-ai-quality"),
    "velvet_bot/ai_vision.py": ("process_once", "compensate-claimed-ai-profile"),
    "velvet_bot/calibrated_ai_quality.py": (
        "process_once",
        "compensate-claimed-calibrated-quality",
    ),
}

for path_text, (_, reason) in TARGETS.items():
    path = ROOT / path_text
    text = path.read_text(encoding="utf-8")
    old = "            except Exception as error:\n"
    new = f"            except Exception as error:  # broad-boundary: {reason}\n"
    if new not in text:
        if text.count(old) != 1:
            raise SystemExit(f"Expected one broad catch in {path_text}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")

inventory_path = ROOT / "docs/p2_stability_inventory.json"
data = json.loads(inventory_path.read_text(encoding="utf-8"))
for item in data["broad_exceptions"]:
    target = TARGETS.get(item["path"])
    if target and item["function"] == target[0]:
        item["classification"] = "approved_boundary"
        item["reason"] = target[1]

approved = [
    item for item in data["broad_exceptions"]
    if item["classification"] == "approved_boundary"
]
unresolved = [
    item for item in data["broad_exceptions"]
    if item["classification"] == "unresolved"
]
data.update(
    schema_version=7,
    generated_from_commit="p2e-ai-worker-boundaries",
    broad_exception_approved=len(approved),
    broad_exception_unresolved=len(unresolved),
    broad_exception_unresolved_files=len({item["path"] for item in unresolved}),
    next_slice={
        "target": "velvet_bot/ai_job_runtime.py",
        "kind": "broad_exception_triage",
    },
)
inventory_path.write_text(
    json.dumps(data, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

unresolved_by_file = Counter(item["path"] for item in unresolved)
lines = [
    "# P2 stability inventory",
    "",
    "AST-инвентаризация широких исключений и callback acknowledgment.",
    "",
    "## Сводка",
    "",
    f"- broad exceptions raw: **{data['broad_exception_total']}** в **{data['broad_exception_files']}** файлах;",
    f"- approved orchestration boundaries: **{len(approved)}**;",
    f"- unresolved broad exceptions: **{len(unresolved)}** в **{len(unresolved_by_file)}** файлах;",
    f"- callback handlers: **{data['callback_total']}**;",
    f"- missing/late acknowledgment: **{data['risky_callback_total']}**;",
    f"- guarded acknowledgment: **{data['guarded_callback_total']}**;",
    f"- delegated wrappers: **{data['delegated_callback_total']}**.",
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
lines.extend(
    [
        "",
        "## Risky callbacks",
        "",
        "- Нет. Callback late/missing baseline закрыт.",
        "",
        "## Следующий срез",
        "",
        "- `velvet_bot/ai_job_runtime.py`: broad-exception triage runtime creation boundary.",
        "",
        "## Правило обновления",
        "",
        "Approved boundary требует inline-маркер и отдельный поведенческий тест. Raw count не уменьшается от классификации; unresolved count отражает оставшийся долг.",
        "",
    ]
)
(ROOT / "docs/p2_stability_inventory.md").write_text(
    "\n".join(lines), encoding="utf-8"
)

for name in ("development_status.md", "project_memory.md"):
    path = ROOT / "docs" / name
    text = path.read_text(encoding="utf-8")
    text = text.replace("67 unresolved broad exceptions", "64 unresolved broad exceptions")
    path.write_text(text, encoding="utf-8")

changelog_path = ROOT / "CHANGELOG.md"
changelog = changelog_path.read_text(encoding="utf-8")
entry = (
    "\n### P2E: AI worker boundaries\n\n"
    "- Классифицированы claimed-target compensation boundaries в AI quality, semantic vision и calibrated quality workers.\n"
    "- Unresolved broad baseline уменьшен с 67 до 64.\n"
)
if entry.strip() not in changelog:
    changelog = changelog.replace("## [Unreleased]\n", "## [Unreleased]\n" + entry, 1)
changelog_path.write_text(changelog, encoding="utf-8")
