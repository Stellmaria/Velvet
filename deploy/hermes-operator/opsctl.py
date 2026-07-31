from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://hermes-ops-gateway:8877"
DEFAULT_TOKEN_FILE = "/opt/data/.hermes-ops-client-token"
PROJECT_SERVICES = {
    "velvet": {"bot"},
    "max": {"bot", "userbot"},
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fixed-action control client for the trusted Hermes operator.",
    )
    parser.add_argument("project", choices=sorted(PROJECT_SERVICES))
    parser.add_argument(
        "action",
        choices=("status", "logs", "start", "restart", "update", "rollback"),
    )
    parser.add_argument("service", nargs="?", choices=("bot", "userbot"))
    parser.add_argument("--lines", type=int, default=200)
    return parser


def _token() -> str:
    path = Path(os.getenv("HERMES_OPS_CLIENT_TOKEN_FILE", DEFAULT_TOKEN_FILE))
    value = path.read_text(encoding="utf-8").strip()
    if len(value) < 24:
        raise RuntimeError("Hermes operator client token is missing or invalid")
    return value


def _request(method: str, path: str) -> tuple[int, dict[str, object]]:
    base_url = os.getenv("HERMES_OPS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
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
        raise RuntimeError("Hermes operator gateway is unavailable") from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Hermes operator gateway returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeError("Hermes operator gateway response must be an object")
    return status, payload


def main() -> int:
    args = _parser().parse_args()
    project = str(args.project)
    action = str(args.action)

    if action in {"start", "restart"}:
        if not args.service:
            raise SystemExit(f"{action} requires service: bot or userbot")
        service = str(args.service)
        if service not in PROJECT_SERVICES[project]:
            raise SystemExit(f"{project} does not expose service {service}")
        method = "POST"
        path = f"/v1/{project}/{action}/{service}"
    elif action == "logs":
        method = "GET"
        lines = max(1, min(int(args.lines), 500))
        path = f"/v1/{project}/logs?lines={lines}"
    elif action == "status":
        method = "GET"
        path = f"/v1/{project}/status"
    else:
        if args.service:
            raise SystemExit(f"{action} does not accept a service")
        method = "POST"
        path = f"/v1/{project}/{action}"

    status, payload = _request(method, path)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status < 400 and payload.get("ok") is True else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
