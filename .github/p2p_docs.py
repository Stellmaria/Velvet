from pathlib import Path

root = Path(__file__).resolve().parents[1]
old = "3. P2O: topic archive failure boundary classified; unresolved broad baseline 45 → 44."
new = "3. P2P: backup center callback boundary hardened; unresolved broad baseline 44 → 43."
for name in ("development_status.md", "project_memory.md"):
    path = root / "docs" / name
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(name)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

path = root / "CHANGELOG.md"
text = path.read_text(encoding="utf-8")
entry = """
### P2P: backup center callback boundary

- Preserved the original unexpected backup error when Telegram cannot render the error message.
- Classified the backup callback reporting boundary.
- Unresolved broad baseline decreased from 44 to 43.
"""
if entry.strip() not in text:
    text = text.replace("## [Unreleased]\n", "## [Unreleased]\n" + entry, 1)
path.write_text(text, encoding="utf-8")
