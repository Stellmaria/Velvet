from pathlib import Path

root = Path(__file__).resolve().parents[1]
old = "3. P2M: error center boundaries classified; unresolved broad baseline 51 → 47."
new = "3. P2N: admin media preview boundaries classified; unresolved broad baseline 47 → 45."
for name in ("development_status.md", "project_memory.md"):
    path = root / "docs" / name
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(name)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

path = root / "CHANGELOG.md"
text = path.read_text(encoding="utf-8")
entry = """
### P2N: admin media preview boundaries

- Classified two administrative preview fallback boundaries.
- Unresolved broad baseline decreased from 47 to 45.
"""
if entry.strip() not in text:
    text = text.replace("## [Unreleased]\n", "## [Unreleased]\n" + entry, 1)
path.write_text(text, encoding="utf-8")
