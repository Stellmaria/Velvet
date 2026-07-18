from pathlib import Path

root = Path(__file__).resolve().parents[1]
old = "3. P2P: backup center callback boundary hardened; unresolved broad baseline 44 → 43."
new = "3. P2Q: channel analytics ingest boundary classified; unresolved broad baseline 43 → 42."
for name in ("development_status.md", "project_memory.md"):
    path = root / "docs" / name
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(name)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

path = root / "CHANGELOG.md"
text = path.read_text(encoding="utf-8")
entry = """
### P2Q: channel analytics ingest boundary

- Classified channel post analytics ingest failure reporting.
- Added tracked-channel, audit-context and cancellation tests.
- Unresolved broad baseline decreased from 43 to 42.
"""
if entry.strip() not in text:
    text = text.replace("## [Unreleased]\n", "## [Unreleased]\n" + entry, 1)
path.write_text(text, encoding="utf-8")
