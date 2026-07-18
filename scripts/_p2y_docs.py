from pathlib import Path

old = "3. P2X: publication failure reporting uses source/private fallback and preserves the original error; unresolved broad baseline 27 → 26."
new = "3. P2Y: quality duplicate safe edit catches only TelegramBadRequest; raw broad baseline 70 → 69 and unresolved 26 → 25."
for name in ("docs/development_status.md", "docs/project_memory.md"):
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"status line not found in {name}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

path = Path("CHANGELOG.md")
text = path.read_text(encoding="utf-8")
entry = """### P2Y: quality duplicate safe edit

- Duplicate list edits now catch only TelegramBadRequest.
- Runtime failures and cancellation are no longer swallowed by a Telegram-specific fallback.
- Raw broad baseline decreased from 70 to 69; unresolved decreased from 26 to 25.

"""
marker = "## [Unreleased]\n\n"
if marker not in text:
    raise SystemExit("changelog marker not found")
path.write_text(text.replace(marker, marker + entry, 1), encoding="utf-8")
