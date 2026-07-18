from pathlib import Path

replacements = {
    "docs/development_status.md": (
        "3. P2S: error-center markup cleanup is observable; unresolved broad baseline 40 → 39.",
        "3. P2T: Guest Mode delivery failures are reported once; unresolved broad baseline 39 → 37.",
    ),
    "docs/project_memory.md": (
        "3. P2S: error-center markup cleanup is observable; unresolved broad baseline 40 → 39.",
        "3. P2T: Guest Mode delivery failures are reported once; unresolved broad baseline 39 → 37.",
    ),
}

for name, (old, new) in replacements.items():
    path = Path(name)
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"missing documentation marker: {name}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

changelog = Path("CHANGELOG.md")
text = changelog.read_text(encoding="utf-8")
marker = "## [Unreleased]\n"
entry = """

### P2T: guest archive boundaries

- Guest topic delivery failures now create one specific audit incident instead of a specific and a generic duplicate.
- General Guest Mode failures still create one generic audit incident and return a user-facing response.
- Cancellation continues to propagate.
- Unresolved broad baseline decreased from 39 to 37.
"""
if marker not in text:
    raise SystemExit("missing changelog marker")
changelog.write_text(text.replace(marker, marker + entry, 1), encoding="utf-8")
