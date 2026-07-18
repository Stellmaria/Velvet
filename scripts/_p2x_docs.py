from pathlib import Path

old = "3. P2W: manager download reporting is separated from callback acknowledgment; unresolved broad baseline 28 → 27."
new = "3. P2X: publication failure reporting uses source/private fallback and preserves the original error; unresolved broad baseline 27 → 26."
for name in ("docs/development_status.md", "docs/project_memory.md"):
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"status line not found in {name}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

path = Path("CHANGELOG.md")
text = path.read_text(encoding="utf-8")
entry = """### P2X: publication report boundary

- Publication failures retain a local traceback and use source-chat or private fallback reporting.
- Telegram reporting failures no longer replace the original publication failure.
- Unresolved broad baseline decreased from 27 to 26.

"""
marker = "## [Unreleased]\n\n"
if marker not in text:
    raise SystemExit("changelog marker not found")
path.write_text(text.replace(marker, marker + entry, 1), encoding="utf-8")
