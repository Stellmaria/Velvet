from pathlib import Path

old = "3. P2Y: quality duplicate safe edit catches only TelegramBadRequest; raw broad baseline 70 → 69 and unresolved 26 → 25."
new = "3. P2Z: manual quality jobs compensate failures and preserve cancellation; unresolved broad baseline 25 → 24."
for name in ("docs/development_status.md", "docs/project_memory.md"):
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"status line not found in {name}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

path = Path("CHANGELOG.md")
text = path.read_text(encoding="utf-8")
entry = """### P2Z: manual quality job boundary

- Manual quality failures compensate the created AI job with an error state.
- Cancellation records an interrupted job and continues to propagate.
- Unresolved broad baseline decreased from 25 to 24.

"""
marker = "## [Unreleased]\n\n"
if marker not in text:
    raise SystemExit("changelog marker not found")
path.write_text(text.replace(marker, marker + entry, 1), encoding="utf-8")
