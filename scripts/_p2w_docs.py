from pathlib import Path

current = (
    "3. P2V: public archive persistence and Telegram presentation are separated; "
    "unresolved broad baseline 33 → 28."
)
updated = (
    "3. P2W: manager download reporting is separated from callback acknowledgment; "
    "unresolved broad baseline 28 → 27."
)
for name in ("docs/development_status.md", "docs/project_memory.md"):
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    if current not in text:
        raise RuntimeError(f"missing current P2 line in {name}")
    path.write_text(text.replace(current, updated, 1), encoding="utf-8")

path = Path("CHANGELOG.md")
text = path.read_text(encoding="utf-8")
anchor = "## [Unreleased]\n"
entry = """

### P2W: public manager download boundary

- Manager original delivery is separated from callback success reporting.
- Callback-answer failure no longer turns a completed delivery into a false send failure.
- Unresolved broad baseline decreased from 28 to 27.
"""
if anchor not in text:
    raise RuntimeError("missing changelog anchor")
path.write_text(text.replace(anchor, anchor + entry, 1), encoding="utf-8")
