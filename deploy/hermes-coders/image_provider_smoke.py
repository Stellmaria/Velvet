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
_SECRET = re.compile(
    r"(?i)(authorization\s*:\s*bearer\s+|"
    r"[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Z0-9_]*\s*[=:]\s*)"
    r"[^\s,;]+"
)
_PROBE = r'''
import hmac
import json
import os
import urllib.request


def models_for(key):
    request = urllib.request.Request(
        "https://byesu.com/v1/models",
        headers={
            "Authorization": "Bearer " + key,
            "Accept": "application/json",
            "User-Agent": "velvet-image-provider-smoke",
        },
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.load(response)
    items = payload.get("data") if isinstance(payload, dict) else []
    return {
        str(item.get("id"))
        for item in items or []
        if isinstance(item, dict) and item.get("id")
    }


enabled = os.environ.get(
    "CODEX_IMAGE_BYESU_FALLBACK_ENABLED", "false"
).strip().casefold() in {"1", "true", "yes", "on", "да"}
if not enabled:
    print(json.dumps({"enabled": False}))
    raise SystemExit(0)

analysis = os.environ.get("BYESU_HERMES_CODEX_API_KEY", "").strip()
media = os.environ.get("BYESU_MEDIA_GEN_API_KEY", "").strip()
if len(analysis) < 20 or len(media) < 20:
    raise SystemExit("image provider credentials missing")
if hmac.compare_digest(analysis, media):
    raise SystemExit("image provider credentials must be distinct")

analysis_models = models_for(analysis)
media_models = models_for(media)
print(
    json.dumps(
        {
            "enabled": True,
            "distinct": True,
            "analysis": {
                name: name in analysis_models
                for name in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
            },
            "media": {
                name: name in media_models
                for name in ("gpt-image-2", "firefly-gpt-image-2")
            },
        },
        ensure_ascii=False,
    )
)
'''


class ImageProviderSmokeError(RuntimeError):
    pass


def redact(value: str) -> str:
    return _SECRET.sub(r"\1[REDACTED]", value)


def validate(payload: dict[str, Any]) -> str:
    if payload.get("enabled") is False:
        return "IMAGE_FALLBACK_DISABLED"
    if payload.get("enabled") is not True or payload.get("distinct") is not True:
        raise ImageProviderSmokeError("image provider split-key contract unavailable")
    analysis = payload.get("analysis")
    media = payload.get("media")
    if not isinstance(analysis, dict) or not isinstance(media, dict):
        raise ImageProviderSmokeError("image provider capability payload incomplete")
    missing_analysis = [
        name
        for name in ("gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna")
        if analysis.get(name) is not True
    ]
    if missing_analysis:
        raise ImageProviderSmokeError(
            "Hermes-Codex key missing image analysis models: "
            + ", ".join(missing_analysis)
        )
    missing_media = [
        name
        for name in ("gpt-image-2", "firefly-gpt-image-2")
        if media.get(name) is not True
    ]
    if missing_media:
        raise ImageProviderSmokeError(
            "Media Gen key missing image generation models: "
            + ", ".join(missing_media)
        )
    return "SPLIT_KEYS_OK, ANALYSIS_MODELS_OK, MEDIA_MODELS_OK"


def main() -> int:
    result = subprocess.run(
        [*_COMPOSE, "exec", "-T", "hermes-coder-velvet", "python", "-c", _PROBE],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        details = redact((result.stderr or result.stdout).strip()[-2000:])
        raise ImageProviderSmokeError(f"Velvet image provider probe failed: {details}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise ImageProviderSmokeError("Velvet image provider probe returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise ImageProviderSmokeError("Velvet image provider probe returned non-object")
    print("Velvet GPT Image 2 provider:", validate(payload))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, subprocess.TimeoutExpired, ImageProviderSmokeError) as error:
        print(f"Hermes image provider smoke failed: {error}", file=sys.stderr)
        raise SystemExit(2)
