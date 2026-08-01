from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BASE_URL = "http://hermes-monitor-gateway:8879"
DEFAULT_TOKEN_FILE = "/opt/data/.hermes-ops-client-token"
VIEWS = ("summary", "resources", "containers", "services", "gpu", "models", "processes", "incidents")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only host monitoring client for Kael.")
    parser.add_argument("view", choices=VIEWS)
    return parser


def _token() -> str:
    path = Path(os.getenv("HERMES_OPS_CLIENT_TOKEN_FILE", DEFAULT_TOKEN_FILE))
    value = path.read_text(encoding="utf-8").strip()
    if len(value) < 24:
        raise RuntimeError("Hermes operator client token is missing or invalid")
    return value


def main() -> int:
    args = _parser().parse_args()
    base_url = os.getenv("HERMES_MONITOR_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
    request = Request(
        f"{base_url}/v1/monitor/{args.view}",
        method="GET",
        headers={
            "Authorization": f"Bearer {_token()}",
            "Accept": "application/json",
            "Connection": "close",
        },
    )
    try:
        with urlopen(request, timeout=45) as response:
            status = int(response.status)
            raw = response.read(512 * 1024)
    except HTTPError as error:
        status = int(error.code)
        raw = error.read(512 * 1024)
    except (URLError, TimeoutError, OSError) as error:
        raise RuntimeError("Hermes monitor gateway is unavailable") from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RuntimeError("Hermes monitor gateway returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeError("Hermes monitor gateway response must be an object")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if status < 400 and payload.get("ok") is True else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from error
