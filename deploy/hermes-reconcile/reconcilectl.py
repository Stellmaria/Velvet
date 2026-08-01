from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://hermes-reconcile-gateway:8878"
DEFAULT_TOKEN_FILE = "/opt/data/.hermes-ops-client-token"
TARGETS = ("coders", "entities", "librarian", "all")
_TERMINAL = {"completed", "failed"}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fixed-target Hermes infrastructure reconcile client.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    submit = subparsers.add_parser("submit")
    submit.add_argument("target", choices=TARGETS)
    status = subparsers.add_parser("status")
    status.add_argument("task_id")
    wait = subparsers.add_parser("wait")
    wait.add_argument("task_id")
    wait.add_argument("--interval", type=float, default=5.0)
    subparsers.add_parser("list")
    return parser


def _token() -> str:
    path = Path(os.getenv("HERMES_OPS_CLIENT_TOKEN_FILE", DEFAULT_TOKEN_FILE))
    value = path.read_text(encoding="utf-8").strip()
    if len(value) < 24:
        raise RuntimeError("Hermes operator client token is missing or invalid")
    return value


def _request(method: str, path: str) -> tuple[int, dict[str, object]]:
    base_url = os.getenv("HERMES_RECONCILE_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    request = Request(
        f"{base_url}{path}",
        data=b"{}" if method == "POST" else None,
        method=method,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Connection": "close",
        },
    )
    try:
        with urlopen(request, timeout=35) as response:
            status = int(response.status)
            raw = response.read(512 * 1024)
    except HTTPError as error:
        status = int(error.code)
        raw = error.read(512 * 1024)
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError("Hermes reconcile gateway is unavailable") from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Hermes reconcile gateway returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeError("Hermes reconcile gateway response must be an object")
    return status, payload


def _print(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def main() -> int:
    args = _parser().parse_args()
    command = str(args.command)
    if command == "submit":
        status, payload = _request("POST", f"/v1/reconcile/{args.target}")
    elif command == "status":
        status, payload = _request("GET", f"/v1/tasks/{args.task_id}")
    elif command == "list":
        status, payload = _request("GET", "/v1/tasks")
    else:
        interval = max(1.0, min(float(args.interval), 60.0))
        while True:
            status, payload = _request("GET", f"/v1/tasks/{args.task_id}")
            task_status = str(payload.get("status", ""))
            if status >= 400 or task_status in _TERMINAL:
                break
            time.sleep(interval)
    _print(payload)
    return 0 if status < 400 and payload.get("ok") is True else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
