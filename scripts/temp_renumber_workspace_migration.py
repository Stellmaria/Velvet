from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
CURRENT = MIGRATIONS / "103_workspaces.sql"


def replace_all(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"Expected {old!r} in {path}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def migration_number(path: Path) -> int | None:
    prefix, separator, _ = path.name.partition("_")
    if not separator or not prefix.isdigit():
        return None
    return int(prefix)


def main() -> None:
    if not CURRENT.is_file():
        raise RuntimeError("Current workspace migration is missing")

    occupied = {
        number
        for path in MIGRATIONS.glob("*.sql")
        if path != CURRENT
        if (number := migration_number(path)) is not None
        and number < 900_000
    }
    candidate = max(occupied, default=0) + 1
    while candidate in occupied:
        candidate += 1

    target_name = f"{candidate:03d}_workspaces.sql"
    target = MIGRATIONS / target_name
    if target.exists():
        raise RuntimeError(f"Migration target already exists: {target_name}")
    CURRENT.replace(target)

    replace_all(
        ROOT / "tests/test_workspace_foundation.py",
        'migrations/103_workspaces.sql',
        f'migrations/{target_name}',
    )
    replace_all(
        ROOT / "docs/worklog/2026-07-21-workspace-foundation.md",
        '`103_workspaces.sql`',
        f'`{target_name}`',
    )

    (ROOT / "scripts/temp_renumber_workspace_migration.py").unlink()
    (ROOT / ".github/workflows/temp-renumber-workspace-migration.yml").unlink()


if __name__ == "__main__":
    main()
