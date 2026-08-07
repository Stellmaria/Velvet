#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from codex_availability import CodexAvailabilityError, CodexAvailabilityGate
from codex_runner import read_codex_subscription_rate_limits


def _gate() -> CodexAvailabilityGate:
    codex_bin = os.environ.get("CODEX_BIN", "codex").strip() or "codex"
    codex_home = Path(os.environ.get("CODEX_HOME", "/opt/codex")).resolve()
    run_root = Path(os.environ.get("CODEX_RUN_ROOT", "/opt/codex-runs")).resolve()

    def probe() -> dict[str, Any]:
        return read_codex_subscription_rate_limits(
            codex_bin,
            codex_home,
            timeout_seconds=12,
        )

    return CodexAvailabilityGate(root=run_root, probe=probe)


def _iso(value: object) -> str | None:
    if isinstance(value, bool):
        return None
    try:
        epoch = int(float(value))
    except (TypeError, ValueError):
        return None
    if epoch <= 0:
        return None
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat()


def _render(state: dict[str, Any]) -> dict[str, Any]:
    return {
        **state,
        "project": os.environ.get("HERMES_CODER_PROJECT", "unknown"),
        "codex_available_at_iso": _iso(state.get("codex_available_at")),
        "manual_hold_until_iso": _iso(state.get("manual_hold_until")),
        "last_checked_at_iso": _iso(state.get("last_checked_at")),
        "next_periodic_check_at_iso": _iso(state.get("next_periodic_check_at")),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Управление динамическим Codex subscription availability state."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("refresh")
    hold = commands.add_parser("hold")
    hold.add_argument(
        "--until",
        required=True,
        help="auto, Unix epoch или ISO-8601 timestamp",
    )
    commands.add_parser("clear")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        gate = _gate()
        if args.command == "status":
            state = gate.status()
        elif args.command == "refresh":
            state = gate.refresh(source="operator_refresh")
        elif args.command == "hold":
            state = gate.hold(args.until)
        elif args.command == "clear":
            state = gate.clear()
        else:  # pragma: no cover
            raise CodexAvailabilityError(f"Неизвестная команда: {args.command}")
        print(json.dumps(_render(state), ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except CodexAvailabilityError as error:
        print(
            json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False),
            file=os.sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
