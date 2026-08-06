#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

_SOURCE_DIR = Path(__file__).resolve().parent
_COMPOSE = (
    "docker",
    "compose",
    "--project-name",
    "hermes-coders",
    "--profile",
    "velvet",
    "--profile",
    "max",
    "-f",
    str(_SOURCE_DIR / "compose.yaml"),
    "-f",
    str(_SOURCE_DIR / "compose.runtime.yaml"),
    "-f",
    str(_SOURCE_DIR / "compose.security.yaml"),
)
_EXPECTED_ROUTES = {
    "small_general": ["gpt-5.6-luna", "gpt-5.6-terra"],
    "small_code": ["gpt-5.4-mini", "gpt-5.6-terra"],
    "standard": ["gpt-5.6-terra"],
    "complex": ["gpt-5.6-terra"],
    "high_risk": ["gpt-5.6-terra"],
}
_EXPECTED_CREDENTIAL_GROUPS = [
    {
        "name": "byesu-coder",
        "models": ["gpt-5.4-mini", "gpt-5.6-terra", "gpt-5.6-luna"],
    }
]
_SECRET = re.compile(
    r"(?i)(authorization\s*:\s*bearer\s+|"
    r"[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Z0-9_]*\s*[=:]\s*)"
    r"[^\s,;]+"
)
_PROBE = r'''
import json
import os
import urllib.error
import urllib.request


def request_json(url, headers):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.load(response)


def model_access(env_name, required):
    key = os.environ.get(env_name, "").strip()
    if not key:
        return {"configured": False, "models": {name: False for name in required}}
    payload = request_json(
        "https://byesu.com/v1/models",
        {
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": "velvet-tier-provider-smoke",
        },
    )
    items = payload.get("data") if isinstance(payload, dict) else None
    ids = {
        str(item.get("id"))
        for item in items or []
        if isinstance(item, dict) and item.get("id")
    }
    return {
        "configured": True,
        "models": {name: name in ids for name in required},
    }

capabilities = request_json(
    "http://127.0.0.1:8642/v1/capabilities",
    {
        "Authorization": "Bearer " + os.environ["CODEX_RUNNER_API_KEY"],
        "Accept": "application/json",
    },
)
result = {
    "capabilities": capabilities,
    "availability": {
        "byesu-shared": model_access(
            "BYESU_HERMES_CODEX_API_KEY",
            ("gpt-5.4-mini", "gpt-5.6-terra", "gpt-5.6-luna"),
        ),
    },
}
print(json.dumps(result, ensure_ascii=False))
'''


class TierProviderSmokeError(RuntimeError):
    pass


def redact(value: str) -> str:
    return _SECRET.sub(r"\1[REDACTED]", value)


def validate_payload(project: str, payload: dict[str, Any]) -> str:
    capabilities = payload.get("capabilities")
    if not isinstance(capabilities, dict):
        raise TierProviderSmokeError(f"{project}: capabilities missing")
    routing = capabilities.get("routing")
    if not isinstance(routing, dict):
        raise TierProviderSmokeError(f"{project}: routing missing")
    if routing.get("downgrade_allowed") is not False:
        raise TierProviderSmokeError(f"{project}: downgrade is not explicitly blocked")
    audit = routing.get("mutation_audit")
    if not isinstance(audit, dict):
        raise TierProviderSmokeError(f"{project}: mutation audit missing")
    if audit.get("successful_runs") is not True:
        raise TierProviderSmokeError(f"{project}: successful mutations are not audited")
    if audit.get("read_only_fail_closed") is not True:
        raise TierProviderSmokeError(f"{project}: read-only mutation does not fail closed")
    fallback = routing.get("provider_fallback")
    if not isinstance(fallback, dict):
        raise TierProviderSmokeError(f"{project}: provider fallback missing")
    if fallback.get("enabled") is not True:
        raise TierProviderSmokeError(f"{project}: provider fallback disabled")
    if fallback.get("routes_by_tier") != _EXPECTED_ROUTES:
        raise TierProviderSmokeError(f"{project}: unexpected routes_by_tier")
    if fallback.get("credential_groups") != _EXPECTED_CREDENTIAL_GROUPS:
        raise TierProviderSmokeError(f"{project}: credentials are not unified")
    if fallback.get("after_mutation") is not False:
        raise TierProviderSmokeError(f"{project}: mutation retry is not blocked")
    if fallback.get("after_execution_event") is not False:
        raise TierProviderSmokeError(f"{project}: execution-event retry is not blocked")
    if fallback.get("model_access_failure") != "fail_closed":
        raise TierProviderSmokeError(f"{project}: model access does not fail closed")

    public = json.dumps(capabilities, ensure_ascii=False).casefold()
    for forbidden in ("env_key", "api_key", "authorization", "bearer "):
        if forbidden in public:
            raise TierProviderSmokeError(
                f"{project}: capabilities expose forbidden marker {forbidden}"
            )

    availability = payload.get("availability")
    if not isinstance(availability, dict):
        raise TierProviderSmokeError(f"{project}: provider availability missing")
    shared = availability.get("byesu-shared")
    if not isinstance(shared, dict) or shared.get("configured") is not True:
        raise TierProviderSmokeError(f"{project}: shared Byesu credential unavailable")
    models = shared.get("models") if isinstance(shared.get("models"), dict) else {}
    if models.get("gpt-5.6-terra") is not True:
        raise TierProviderSmokeError(f"{project}: Terra unavailable to shared key")
    if models.get("gpt-5.6-luna") is not True:
        raise TierProviderSmokeError(f"{project}: Luna unavailable to shared key")
    mini = models.get("gpt-5.4-mini") is True
    return "MINI_AVAILABLE" if mini else "MINI_UNAVAILABLE_FAIL_CLOSED"


def read_payload(service: str) -> dict[str, Any]:
    result = subprocess.run(
        [*_COMPOSE, "exec", "-T", service, "python", "-c", _PROBE],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        details = redact((result.stderr or result.stdout).strip()[-2000:])
        raise TierProviderSmokeError(f"{service}: probe failed: {details}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise TierProviderSmokeError(f"{service}: invalid JSON") from error
    if not isinstance(payload, dict):
        raise TierProviderSmokeError(f"{service}: payload is not an object")
    return payload


def main() -> int:
    outcomes: list[str] = []
    for project, service in (
        ("velvet", "hermes-coder-velvet"),
        ("max", "hermes-coder-max"),
    ):
        mini_state = validate_payload(project, read_payload(service))
        outcomes.append(mini_state)
        print(
            f"{project}: TIER_ROUTES_OK, TERRA_OK, LUNA_OK, {mini_state}, "
            "ONE_BYESU_KEY_OK, NO_DOWNGRADE_OK, RETRY_GUARDS_OK, MUTATION_AUDIT_OK"
        )
    if len(set(outcomes)) != 1:
        raise TierProviderSmokeError(
            "Velvet and Max expose different Mini availability states"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired, TierProviderSmokeError) as error:
        print(f"Hermes tier provider smoke failed: {error}", file=sys.stderr)
        raise SystemExit(2)
