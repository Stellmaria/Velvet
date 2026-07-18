from pathlib import Path

root = Path(__file__).resolve().parents[1]
old = "3. P2Q: channel analytics ingest boundary classified; unresolved broad baseline 43 → 42."
new = "3. P2R: character create/topic failures are logged; unresolved broad baseline 42 → 40."
for name in ("development_status.md", "project_memory.md"):
    path = root / "docs" / name
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(name)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

path = root / "CHANGELOG.md"
text = path.read_text(encoding="utf-8")
entry = """
### P2R: character topic boundaries

- Unexpected character create and topic binding failures now retain local tracebacks.
- Classified two user-facing handler boundaries.
- Unresolved broad baseline decreased from 42 to 40.
"""
if entry.strip() not in text:
    text = text.replace("## [Unreleased]\n", "## [Unreleased]\n" + entry, 1)
path.write_text(text, encoding="utf-8")
