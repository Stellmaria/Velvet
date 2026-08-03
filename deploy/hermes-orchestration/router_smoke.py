#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from typing import Any

_COMPOSE = ("docker", "compose", "-f", "compose.yaml")
_SECRET = re.compile(
    r"(?i)(authorization\s*:\s*bearer\s+|"
    r"[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Z0-9_]*\s*[=:]\s*)"
    r"[^\s,;]+"
)
_PROBE = r'''
import json
import os
import urllib.request

base = "http://127.0.0.1:8878"
token = os.environ.get("HERMES_CODER_ROUTER_CLIENT_TOKEN", "").strip()
if len(token) < 24:
    raise SystemExit("router client token missing")


def get(path, authenticated=False):
    headers = {"Accept": "application/json"}
    if authenticated:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(base + path, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)

print(
    json.dumps(
        {
            "health": get("/health"),
            "velvet": get("/v1/coders/velvet/capabilities", True),
            "max": get("/v1/coders/max/capabilities", True),
        },
        ensure_ascii=False,
    )
)
'''


class RouterSmokeError(RuntimeError):
    pass


def redact(value: str) -> str:
    return _SECRET.sub(r"\1[REDACTED]", value)


def public_routes(project: str, payload: dict[str, Any]) -> dict[str, Any]:
    routing = payload.get("routing")
    if not isinstance(routing, dict):
        raise RouterSmokeError(f"{project}: routing capabilities missing")
    routes = routing.get("routes_by_tier")
    if not isinstance(routes, dict):
        raise RouterSmokeError(f"{project}: routes_by_tier missing")
    if set(routes) != {"small", "standard", "complex", "high_risk"}:
        raise RouterSmokeError(f"{project}: unexpected tier set")
    if routing.get("downgrade_allowed") is not False:
        raise RouterSmokeError(f"{project}: downgrade is not blocked")
    public = json.dumps(routing, ensure_ascii=False).casefold()
    for forbidden in ("env_key", "api_key", "authorization", "bearer "):
        if forbidden in public:
            raise RouterSmokeError(
                f"{project}: routing exposes forbidden marker {forbidden}"
            )
    return routes


def validate(payload: dict[str, Any]) -> None:
    health = payload.get("health")
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise RouterSmokeError("router health is not ok")
    if health.get("coders") != {"velvet": True, "max": True}:
        raise RouterSmokeError("both coders are not configured")
    velvet = payload.get("velvet")
    maximum = payload.get("max")
    if not isinstance(velvet, dict) or not isinstance(maximum, dict):
        raise RouterSmokeError("coder capabilities missing")
    if public_routes("velvet", velvet) != public_routes("max", maximum):
        raise RouterSmokeError("Velvet and Max routes_by_tier differ")


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
                try:
                    payload = json.loads(result.stdout)
                    if not isinstance(payload, dict):
                        raise RouterSmokeError("payload is not an object")
                    validate(payload)
                except (json.JSONDecodeError, RouterSmokeError) as error:
                    last_error = str(error)
                else:
                    print(
                        "router: HEALTH_OK, VELVET_MAX_PARITY_OK, "
                        "ROUTES_BY_TIER_OK, NO_SECRETS_OK"
                    )
                    return 0
            else:
                last_error = redact((result.stderr or result.stdout).strip()[-2000:])
        time.sleep(2)
    print(f"Hermes coder router smoke failed: {last_error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
