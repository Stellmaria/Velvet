#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("HERMES_CODERS_ROOT", "/srv/hermes-coders")).resolve()
_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_PROJECTS = ("velvet", "max")


class IdleError(RuntimeError):
    pass


def active_ledger_runs() -> list[str]:
    active: list[str] = []
    for project in _PROJECTS:
        run_root = ROOT / "codex-runs" / project
        if not run_root.exists():
            continue
        for path in sorted(run_root.glob("*.json")):
            if path.is_symlink() or not path.is_file():
                raise IdleError(f"unsafe run ledger entry: {path}")
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise IdleError(f"damaged run ledger entry: {path}") from error
            if not isinstance(payload, dict):
                raise IdleError(f"invalid run ledger entry: {path}")
            status = str(payload.get("status") or "")
            run_id = str(payload.get("run_id") or path.stem)
            if status not in _TERMINAL:
                active.append(f"{project}:{run_id}:{status or 'unknown'}")
    return active


def active_sandbox_containers() -> list[str]:
    try:
        result = subprocess.run(
            ["docker", "ps", "-q", "--filter", "label=hermes.sandbox=1"],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise IdleError("could not inspect active sandbox containers") from error
    if result.returncode != 0:
        raise IdleError("could not inspect active sandbox containers")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    ledger = active_ledger_runs()
    containers = active_sandbox_containers()
    if ledger or containers:
        details = []
        if ledger:
            details.append("active ledger runs: " + ", ".join(ledger))
        if containers:
            details.append(f"active sandbox containers: {len(containers)}")
        raise IdleError("; ".join(details))
    print("Hermes sandbox idle gate: PASS")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except IdleError as error:
        print(f"Hermes sandbox idle gate failed: {error}", file=sys.stderr)
        raise SystemExit(2)
