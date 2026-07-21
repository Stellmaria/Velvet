from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def update_changelog() -> None:
    path = ROOT / "CHANGELOG.md"
    text = path.read_text(encoding="utf-8")
    marker = "## [Unreleased]\n"
    section = """## [Unreleased]

### P3A: current architecture status synchronization

- Current status, project memory and architecture audit now reflect merged `main`.
- P2 generated baseline is 76 approved broad boundaries, 0 unresolved and 98 callback handlers with 0 late/missing acknowledgments.
- Legacy handler files, implementations and aliases are 0; four Telegram bundles register 60 active routers without duplicates.
- P3E is complete with 30 domain repositories, 1 PostgreSQL infrastructure adapter, 0 central repositories and 0 root repositories.
- Architecture inventory now points to the first bounded P3F static-typing baseline.

### Owner diagnostics and AI quality hotfixes

- Added owner-only `Velvet Diagnostic Bundle v1` with redacted runtime, workers, Error Center incidents and bounded log tail.
- Added five-minute critical diagnostics with per-incident and global cooldowns.
- Qwen retry now resets `media_ai_profiles.analysis` to an empty JSON object instead of violating its `NOT NULL` constraint.
- Permanent oversized/no-preview calibrated AI skips are logged as `INFO`; real provider, database and filesystem failures remain `WARNING/ERROR`.
"""
    if marker not in text:
        raise RuntimeError("CHANGELOG.md does not contain Unreleased marker")
    if "### P3A: current architecture status synchronization" in text:
        return
    path.write_text(text.replace(marker, section, 1), encoding="utf-8")


def update_inventory_generator() -> None:
    path = ROOT / "scripts" / "inventory_architecture_layout.py"
    text = path.read_text(encoding="utf-8")
    old = '''        "next_slice": {
            "phase": "P3E",
            "target": "repository and root-module layout normalization",
            "strategy": "inventory repository consumers, then migrate one domain per reviewed slice",
        },'''
    new = '''        "next_slice": {
            "phase": "P3F",
            "target": "bounded static typing baseline",
            "strategy": "type-check one transport-neutral package, gate new errors, then expand scope",
        },'''
    if new in text:
        return
    if old not in text:
        raise RuntimeError("architecture inventory next-slice block not found")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> None:
    update_changelog()
    update_inventory_generator()


if __name__ == "__main__":
    main()
