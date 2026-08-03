#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SOURCE_DIR = Path(__file__).resolve().parent
ORCHESTRATION_DIR = SOURCE_DIR.parent / "hermes-orchestration"
COMPOSE_FILE = ORCHESTRATION_DIR / "compose.yaml"
_COMPOSE = (
    "docker",
    "compose",
    "--project-directory",
    str(ORCHESTRATION_DIR),
    "-f",
    str(COMPOSE_FILE),
)
_SECRET = re.compile(
    r"(?i)(authorization\s*:\s*bearer\s+|"
    r"[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Z0-9_]*\s*[=:]\s*)"
    r"[^\s,;]+"
)
_PROBE = r'''
import json
import os
import urllib.request


def get(path, token=None):
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(
        "http://127.0.0.1:8878" + path,
        headers=headers,
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)

health = get("/health")
token = os.environ["HERMES_CODER_ROUTER_CLIENT_TOKEN"]
print(
    json.dumps(
        {
            "health": health,
            "velvet": get("/v1/coders/velvet/capabilities", token),
            "max": get("/v1/coders/max/capabilities", token),
        },
        ensure_ascii=False,
    )
)
'''


class RouterSmokeError(RuntimeError):
    pass


def redact(value: str) -> str:
    return _SECRET.sub(r"\1[REDACTED]", value)


def public_routes(payload: dict[str, Any]) -> dict[str, Any]:
    routing = payload.get("routing")
    if not isinstance(routing, dict):
        raise RouterSmokeError("routing capabilities missing")
    routes = routing.get("routes_by_tier")
    if not isinstance(routes, dict):
        raise RouterSmokeError("routes_by_tier missing")
    expected_tiers = {"small", "standard", "complex", "high_risk"}
    if set(routes) != expected_tiers:
        raise RouterSmokeError("unexpected tier set")
    if routing.get("downgrade_allowed") is not False:
        raise RouterSmokeError("downgrade is not blocked")
    public = json.dumps(routing, ensure_ascii=False).casefold()
    for forbidden in ("env_key", "api_key", "authorization", "bearer "):
        if forbidden in public:
            raise RouterSmokeError(f"routing exposes forbidden marker {forbidden}")
    return routes


def validate(payload: dict[str, Any]) -> None:
    health = payload.get("health")
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise RouterSmokeError("router health is not ok")
    coders = health.get("coders")
    if coders != {"velvet": True, "max": True}:
        raise RouterSmokeError("router does not report both coders configured")
    velvet = payload.get("velvet")
    maximum = payload.get("max")
    if not isinstance(velvet, dict) or not isinstance(maximum, dict):
        raise RouterSmokeError("coder capabilities missing")
    velvet_routes = public_routes(velvet)
    max_routes = public_routes(maximum)
    if velvet_routes != max_routes:
        raise RouterSmokeError("Velvet and Max routes_by_tier differ")


def read_payload() -> dict[str, Any]:
    result = subprocess.run(
        [
            *_COMPOSE,
            "exec",
            "-T",
            "hermes-coder-router",
            "python",
            "-c",
            _PROBE,
        ],
        cwd=ORCHESTRATION_DIR,
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
    )
    if result.returncode != 0:
        details = redact((result.stderr or result.stdout).strip()[-2000:])
        raise RouterSmokeError(f"router probe failed: {details}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RouterSmokeError("router probe returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise RouterSmokeError("router payload is not an object")
    return payload


def main() -> int:
    if not COMPOSE_FILE.is_file():
        raise RouterSmokeError(f"orchestration compose missing: {COMPOSE_FILE}")
    validate(read_payload())
    print("router: HEALTH_OK, VELVET_MAX_PARITY_OK, ROUTES_BY_TIER_OK, NO_SECRETS_OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired, RouterSmokeError) as error:
        print(f"Hermes router smoke failed: {error}", file=sys.stderr)
        raise SystemExit(2)
