#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Workspace:
    relative_path: str
    origin: str


WORKSPACES = (
    Workspace("workspaces/velvet", "https://github.com/Stellmaria/Velvet.git"),
    Workspace(
        "workspaces/max",
        "https://github.com/Stellmaria/romatic_club_bot_max.git",
    ),
    Workspace("workspaces/velvet-codex", "https://github.com/Stellmaria/Velvet.git"),
    Workspace(
        "workspaces/max-codex",
        "https://github.com/Stellmaria/romatic_club_bot_max.git",
    ),
)


def chown_tree(root: Path, uid: int, gid: int) -> None:
    os.chown(root, uid, gid, follow_symlinks=False)
    for directory, directory_names, file_names in os.walk(root, followlinks=False):
        base = Path(directory)
        for name in directory_names:
            os.chown(base / name, uid, gid, follow_symlinks=False)
        for name in file_names:
            os.chown(base / name, uid, gid, follow_symlinks=False)


def ownership_needs_repair(root: Path, uid: int, gid: int) -> bool:
    probes = (root, root / ".git", root / ".git" / "config")
    for probe in probes:
        stat_result = probe.stat()
        if stat_result.st_uid != uid or stat_result.st_gid != gid:
            return True
    return False


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-c",
            f"safe.directory={root}",
            "-C",
            str(root),
            *args,
        ],
        check=check,
        capture_output=True,
        text=True,
    )


def reconcile_workspace(root: Path, workspace: Workspace, uid: int, gid: int) -> None:
    target = root / workspace.relative_path
    if not (target / ".git").is_dir():
        raise RuntimeError(f"Workspace не является Git checkout: {target}")

    if ownership_needs_repair(target, uid, gid):
        chown_tree(target, uid, gid)
        print(f"Workspace ownership repaired: {target}")

    current = git(target, "remote", "get-url", "origin", check=False)
    if current.returncode == 0:
        if current.stdout.strip() != workspace.origin:
            git(target, "remote", "set-url", "origin", workspace.origin)
            print(f"Workspace origin normalized: {target}")
    else:
        git(target, "remote", "add", "origin", workspace.origin)
        print(f"Workspace origin added: {target}")


def main() -> int:
    if os.geteuid() != 0:
        print("reconcile_workspaces.py должен запускаться от root", file=sys.stderr)
        return 1

    root = Path(os.environ.get("HERMES_CODERS_ROOT", "/srv/hermes-coders")).resolve()
    uid = int(os.environ.get("HERMES_UID", "10000"))
    gid = int(os.environ.get("HERMES_GID", "10000"))
    if uid <= 0 or gid <= 0:
        print("HERMES_UID и HERMES_GID должны быть положительными", file=sys.stderr)
        return 2

    try:
        for workspace in WORKSPACES:
            reconcile_workspace(root, workspace, uid, gid)
    except (OSError, RuntimeError, subprocess.SubprocessError, ValueError) as exc:
        print(f"Hermes coder workspace reconcile failed: {exc}", file=sys.stderr)
        return 3

    print("Hermes coder workspaces reconciled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
