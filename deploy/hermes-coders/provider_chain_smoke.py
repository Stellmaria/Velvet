#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

_COMPOSE = (
    "docker",
    "compose",
    "--profile",
    "velvet",
    "--profile",
    "max",
    "-f",
    "compose.yaml",
    "-f",
    "compose.runtime.yaml",
)
_EXPECTED_MODELS = ("gpt-5.4-mini", "gpt-5.6-terra", "gpt-5.6-luna")
_EXPECTED_GROUPS = (
    {"name": "byesu-coder", "models": ["gpt-5.4-mini", "gpt-5.6-terra"]},
    {"name": "byesu-gpt-pro", "models": ["gpt-5.6-luna"]},
)
_EXPECTED_PRIMARY = {
    "small": ["gpt-5.6-luna", "gpt-5.6-terra"],
    "standard": ["gpt-5.6-terra"],
    "complex": ["gpt-5.6-sol", "gpt-5.6-terra"],
    "high_risk": ["gpt-5.6-sol", "gpt-5.6-terra"],
}
_EXPECTED_PROVIDER = {
    "small_general": {
        "models": ["gpt-5.6-luna", "gpt-5.6-terra"],
        "degraded": False,
        "review_required": False,
    },
    "small_code": {
        "models": ["gpt-5.4-mini", "gpt-5.6-terra"],
        "degraded": False,
        "review_required": False,
    },
    "standard": {
        "models": ["gpt-5.6-terra"],
        "degraded": False,
        "review_required": False,
    },
    "complex": {
        "models": ["gpt-5.6-terra"],
        "degraded": True,
        "review_required": True,
    },
    "high_risk": {
        "models": ["gpt-5.6-terra"],
        "degraded": True,
        "review_required": True,
    },
}
_PROBE = r'''
import json
import os
import urllib.request

request = urllib.request.Request(
    "http://127.0.0.1:8642/v1/capabilities",
    headers={
        "Authorization": "Bearer " + os.environ["CODEX_RUNNER_API_KEY"],
        "Accept": "application/json",
    },
)
with urllib.request.urlopen(request, timeout=5) as response:
    print(json.dumps(json.load(response), ensure_ascii=False))
'''


class ProviderChainSmokeError(RuntimeError):
    pass


def validate_capabilities(project: str, payload: dict[str, Any]) -> None:
    routing = payload.get("routing")
    if not isinstance(routing, dict):
        raise ProviderChainSmokeError(f"{project}: routing capabilities missing")
    if routing.get("primary_route") != "codex_subscription":
        raise ProviderChainSmokeError(f"{project}: unexpected primary route")
    if routing.get("primary_routes_by_tier") != _EXPECTED_PRIMARY:
        raise ProviderChainSmokeError(f"{project}: unexpected primary tier routes")
    fallback = routing.get("provider_fallback")
    if not isinstance(fallback, dict):
        raise ProviderChainSmokeError(f"{project}: provider fallback missing")
    if fallback.get("enabled") is not True:
        raise ProviderChainSmokeError(f"{project}: provider fallback disabled")
    if fallback.get("route") != "byesu_provider":
        raise ProviderChainSmokeError(f"{project}: unexpected provider route")
    if tuple(fallback.get("models") or ()) != _EXPECTED_MODELS:
        raise ProviderChainSmokeError(f"{project}: unexpected provider model catalog")
    if tuple(fallback.get("credential_groups") or ()) != _EXPECTED_GROUPS:
        raise ProviderChainSmokeError(f"{project}: unexpected credential groups")
    if fallback.get("routes_by_tier") != _EXPECTED_PROVIDER:
        raise ProviderChainSmokeError(f"{project}: unexpected provider tier routes")
    for flag in (
        "after_mutation",
        "after_tool_execution",
        "downgrade_allowed",
        "live_production_mutation",
    ):
        if fallback.get(flag) is not False:
            raise ProviderChainSmokeError(f"{project}: unsafe {flag}")
    public = json.dumps(fallback, ensure_ascii=False).casefold()
    for forbidden in ("env_key", "api_key", "token", "secret"):
        if forbidden in public:
            raise ProviderChainSmokeError(
                f"{project}: capabilities expose forbidden field {forbidden}"
            )


def read_capabilities(service: str) -> dict[str, Any]:
    result = subprocess.run(
        [*_COMPOSE, "exec", "-T", service, "python", "-c", _PROBE],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        details = (result.stderr or result.stdout).strip()[-2000:]
        raise ProviderChainSmokeError(f"{service}: capabilities probe failed: {details}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ProviderChainSmokeError(
            f"{service}: capabilities probe returned invalid JSON"
        ) from error
    if not isinstance(payload, dict):
        raise ProviderChainSmokeError(f"{service}: capabilities payload is not an object")
    return payload


def main() -> int:
    for project, service in (
        ("velvet", "hermes-coder-velvet"),
        ("max", "hermes-coder-max"),
    ):
        validate_capabilities(project, read_capabilities(service))
        print(f"{project}: tier-aware Codex/Byesu routing OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired, ProviderChainSmokeError) as error:
        print(f"Hermes provider routing smoke failed: {error}", file=sys.stderr)
        raise SystemExit(2)
