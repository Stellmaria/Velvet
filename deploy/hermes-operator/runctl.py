#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

_RUN_ID = re.compile(r"^run_[A-Za-z0-9_-]{8,160}$")
_TERMINAL = frozenset({"completed", "failed", "cancelled", "canceled"})


class RunCtlError(RuntimeError):
    pass


def _base_url() -> str:
    value = os.getenv("KAEL_RUNS_BASE_URL", "http://127.0.0.1:8642").strip().rstrip("/")
    if not value.startswith(("http://127.0.0.1:", "http://localhost:")):
        raise RunCtlError("KAEL_RUNS_BASE_URL должен быть loopback URL.")
    return value


def _api_key() -> str:
    value = os.getenv("API_SERVER_KEY", "").strip()
    if len(value) < 24:
        raise RunCtlError("API_SERVER_KEY отсутствует или слишком короткий.")
    return value


def _validate_run_id(value: str) -> str:
    clean = value.strip()
    if not _RUN_ID.fullmatch(clean):
        raise RunCtlError("Некорректный run_id.")
    return clean


def _request(method: str, path: str) -> dict[str, Any]:
    request = urllib.request.Request(
        _base_url() + path,
        data=b"{}" if method == "POST" else None,
        method=method,
        headers={
            "Authorization": "Bearer " + _api_key(),
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")[:1000]
        raise RunCtlError(f"Kael Runs API вернул HTTP {error.code}: {details}") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RunCtlError(f"Kael Runs API недоступен: {type(error).__name__}") from error
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as error:
        raise RunCtlError("Kael Runs API вернул повреждённый JSON.") from error
    if not isinstance(payload, dict):
        raise RunCtlError("Kael Runs API вернул неожиданный тип ответа.")
    return payload


def _safe_payload(payload: dict[str, Any], run_id: str) -> dict[str, Any]:
    status = str(payload.get("status") or "unknown")
    result: dict[str, Any] = {
        "run_id": str(payload.get("run_id") or run_id),
        "status": status,
        "terminal": status.casefold() in _TERMINAL,
    }
    if payload.get("error"):
        result["error"] = str(payload["error"])[:2000]
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Статус и остановка собственных Hermes Runs Каэля.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("status", "stop"):
        command = commands.add_parser(name)
        command.add_argument("run_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        run_id = _validate_run_id(args.run_id)
        if args.command == "status":
            payload = _request("GET", f"/v1/runs/{run_id}")
        else:
            payload = _request("POST", f"/v1/runs/{run_id}/stop")
        safe = _safe_payload(payload, run_id)
        print(json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except RunCtlError as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
