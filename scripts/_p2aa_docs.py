from pathlib import Path

old = "3. P2Z: manual quality jobs compensate failures and preserve cancellation; unresolved broad baseline 25 → 24."
new = "3. P2AA: set-analysis callback and command jobs compensate failures and preserve cancellation; unresolved broad baseline 24 → 22."
for name in ("docs/development_status.md", "docs/project_memory.md"):
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"status line not found in {name}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

path = Path("CHANGELOG.md")
text = path.read_text(encoding="utf-8")
entry = """### P2AA: set analysis job boundaries

- Callback and slash-command set analysis failures compensate their AI jobs.
- Cancellation records interruption and continues to propagate in both paths.
- Unresolved broad baseline decreased from 24 to 22.

"""
marker = "## [Unreleased]\n\n"
if marker not in text:
    raise SystemExit("changelog marker not found")
path.write_text(text.replace(marker, marker + entry, 1), encoding="utf-8")
