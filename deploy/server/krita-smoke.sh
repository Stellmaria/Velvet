#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${1:-${VELVET_ENV_FILE:-.env.server}}"
TIMEOUT_SECONDS="${KRITA_SMOKE_TIMEOUT_SECONDS:-120}"
STABILITY_SECONDS="${KRITA_SMOKE_STABILITY_SECONDS:-3}"

cd "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $APP_DIR/$ENV_FILE" >&2
  exit 2
fi

container_bridge="$(python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys
from scripts.server_preflight import parse_env_file

env = parse_env_file(Path(sys.argv[1]))
bridge_dir = env.get("KRITA_BRIDGE_DIR", "/app/runtime/krita").strip()
if bridge_dir != "/app/runtime/krita" and not bridge_dir.startswith("/app/runtime/krita/"):
    raise SystemExit("KRITA_BRIDGE_DIR must stay inside /app/runtime/krita")
print(bridge_dir)
PY
)"

compose=(
  docker compose
  --env-file "$ENV_FILE"
  -f docker-compose.server.yml
  --profile watermark
)
container_id="$("${compose[@]}" ps -q krita)"
if [[ -z "$container_id" ]]; then
  echo "Krita smoke requires a running krita container" >&2
  exit 1
fi

restart_before="$(docker inspect --format '{{.RestartCount}}' "$container_id")"
smoke_id="server-smoke-$(date -u +%Y%m%dT%H%M%SZ)-$$"

set +e
"${compose[@]}" exec -T krita python3 - \
  "$container_bridge" "$smoke_id" "$TIMEOUT_SECONDS" <<'PY'
from __future__ import annotations

import json
import struct
import sys
import time
import zlib
from pathlib import Path

bridge = Path(sys.argv[1]).resolve()
smoke_id = sys.argv[2]
timeout_seconds = float(sys.argv[3])

for name in ("sources", "requests", "responses", "outputs", "previews", "assets"):
    (bridge / name).mkdir(parents=True, exist_ok=True)

source = bridge / "sources" / f"{smoke_id}.png"
request = bridge / "requests" / f"{smoke_id}.json"
processing = bridge / "requests" / f"{smoke_id}.processing"
response = bridge / "responses" / f"{smoke_id}.json"
output = bridge / "outputs" / f"{smoke_id}.png"


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def cleanup() -> None:
    for path in (request, processing, response, output, source):
        path.unlink(missing_ok=True)


try:
    width = height = 256
    rows = b"".join(
        b"\x00" + bytes((55, 65, 80, 255)) * width for _ in range(height)
    )
    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )
    source.write_bytes(png)

    payload = {
        "schema_version": 2,
        "request_id": smoke_id,
        "job_id": smoke_id,
        "revision": 1,
        "bridge_root": str(bridge),
        "source_path": str(source),
        "response_path": str(response),
        "output_path": str(output),
        "settings": {
            "position": "bottom_right",
            "color": "#ffffff",
            "size": 20.0,
            "margin": 5.0,
            "opacity": 70,
            "lock": True,
        },
        "logo": {"kind": "builtin", "name": "server-smoke"},
    }
    temporary = request.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(request)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline and not response.is_file():
        time.sleep(0.5)
    if not response.is_file():
        raise SystemExit(f"Krita smoke timed out after {timeout_seconds:g}s")

    result = json.loads(response.read_text(encoding="utf-8"))
    if result.get("status") != "ok":
        raise SystemExit(f"Krita smoke failed: {result.get('error') or result}")
    if not output.is_file():
        raise SystemExit(f"Krita smoke output is missing: {output}")
    if not output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
        raise SystemExit("Krita smoke output is not PNG")
    print(f"Krita server smoke succeeded: {output}")
finally:
    cleanup()
PY
smoke_status=$?
set -e

sleep "$STABILITY_SECONDS"

current_id="$("${compose[@]}" ps -q krita)"
if [[ "$current_id" != "$container_id" ]]; then
  echo "Krita container was recreated during smoke test" >&2
  exit 1
fi
if ! restart_after="$(docker inspect --format '{{.RestartCount}}' "$container_id" 2>/dev/null)"; then
  echo "Krita container disappeared during smoke test" >&2
  exit 1
fi
if [[ "$restart_after" != "$restart_before" ]]; then
  echo "Krita restarted during smoke test: $restart_before -> $restart_after" >&2
  exit 1
fi
if (( smoke_status != 0 )); then
  echo "Krita smoke command failed with exit code $smoke_status" >&2
  exit "$smoke_status"
fi
