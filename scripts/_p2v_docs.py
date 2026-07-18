from pathlib import Path

status_line = (
    "3. P2U: media browser fallbacks and failure reporting are verified; "
    "unresolved broad baseline 37 → 33."
)
next_line = (
    "3. P2V: public archive persistence and Telegram presentation are separated; "
    "unresolved broad baseline 33 → 28."
)
for name in ("docs/development_status.md", "docs/project_memory.md"):
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    if status_line not in text:
        raise RuntimeError(f"missing current P2 line in {name}")
    path.write_text(text.replace(status_line, next_line, 1), encoding="utf-8")

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
anchor = "## [Unreleased]\n"
entry = """

### P2V: public archive boundaries

- Classified five public archive failure boundaries and added behavior tests.
- Successful like, subscription, and download operations are no longer reported as failed when Telegram presentation fails afterwards.
- Unresolved broad baseline decreased from 33 to 28.
"""
if anchor not in text:
    raise RuntimeError("missing changelog anchor")
changelog.write_text(text.replace(anchor, anchor + entry, 1), encoding="utf-8")
