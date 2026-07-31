from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _fail(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def main() -> int:
    bridge_dir = Path(os.getenv("KRITA_BRIDGE_DIR", "/app/runtime/krita"))
    heartbeat_path = bridge_dir / "krita-heartbeat.json"
    try:
        max_age = max(
            5.0,
            float(os.getenv("KRITA_SERVER_HEARTBEAT_MAX_AGE_SECONDS", "20")),
        )
    except ValueError:
        return _fail("KRITA_SERVER_HEARTBEAT_MAX_AGE_SECONDS is invalid")

    try:
        payload = json.loads(heartbeat_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _fail(f"Krita heartbeat is missing: {heartbeat_path}")
    except (OSError, json.JSONDecodeError) as error:
        return _fail(f"Krita heartbeat is unreadable: {error}")

    if payload.get("plugin") != "velvet_logo":
        return _fail("Unexpected Krita heartbeat plugin")
    try:
        updated_epoch = float(payload["updated_epoch"])
    except (KeyError, TypeError, ValueError):
        return _fail("Krita heartbeat has no valid updated_epoch")

    age = time.time() - updated_epoch
    if age < -5:
        return _fail(f"Krita heartbeat is from the future: {age:.1f}s")
    if age > max_age:
        return _fail(f"Krita heartbeat is stale: {age:.1f}s > {max_age:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
