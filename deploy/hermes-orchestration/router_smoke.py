#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import time

_COMPOSE = ("docker", "compose", "-f", "compose.yaml")
_PROBE = r'''
import json
import os
import urllib.request

base = "http://127.0.0.1:8878"
token = os.environ.get("HERMES_CODER_ROUTER_CLIENT_TOKEN", "").strip()
if len(token) < 24:
    raise SystemExit("router client token missing")

for project in ("velvet", "max"):
    request = urllib.request.Request(
        f"{base}/v1/coders/{project}/capabilities",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        payload = json.load(response)
    if not isinstance(payload, dict):
        raise SystemExit(f"{project}: invalid capabilities payload")
    routing = payload.get("routing")
    if not isinstance(routing, dict):
        raise SystemExit(f"{project}: routing capabilities missing")
    print(f"{project}: router capabilities OK")
'''


def probe() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*_COMPOSE, "exec", "-T", "hermes-coder-router", "python", "-c", _PROBE],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def main() -> int:
    last_error = "router smoke did not run"
    for _ in range(30):
        try:
            result = probe()
        except (OSError, subprocess.TimeoutExpired) as error:
            last_error = type(error).__name__
        else:
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    clean = line.strip()
                    if clean:
                        print(clean)
                return 0
            last_error = (result.stderr or result.stdout).strip()[-2000:]
        time.sleep(2)
    print(f"Hermes coder router smoke failed: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
