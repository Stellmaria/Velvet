from pathlib import Path

old = "3. P2T: Guest Mode delivery failures are reported once; unresolved broad baseline 39 → 37."
new = "3. P2U: media browser fallbacks and failure reporting are verified; unresolved broad baseline 37 → 33."

for name in ("docs/development_status.md", "docs/project_memory.md"):
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing documentation marker: {name}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
marker = "## [Unreleased]\n"
entry = """

### P2U: media browser boundaries

- Full-size image preview failures fall back to the original archived media.
- Image-document send failures fall back to the original document with caption and navigation preserved.
- Archive page load and delete failures retain audit context and user-facing alerts.
- Cancellation continues to propagate through all four boundaries.
- Unresolved broad baseline decreased from 37 to 33.
"""
if marker not in text:
    raise SystemExit("missing changelog marker")
changelog.write_text(text.replace(marker, marker + entry, 1), encoding="utf-8")
