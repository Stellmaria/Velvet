#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${1:-${VELVET_ENV_FILE:-.env.server}}"
TIMEOUT_SECONDS="${KRITA_SMOKE_TIMEOUT_SECONDS:-120}"

cd "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $APP_DIR/$ENV_FILE" >&2
  exit 2
fi

readarray -t settings < <(python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys
from scripts.server_preflight import parse_env_file

env = parse_env_file(Path(sys.argv[1]))
data_dir = env.get("VELVET_DATA_DIR", "").strip()
bridge_dir = env.get("KRITA_BRIDGE_DIR", "/app/runtime/krita").strip()
if not data_dir:
    raise SystemExit("VELVET_DATA_DIR is missing")
if bridge_dir != "/app/runtime/krita" and not bridge_dir.startswith("/app/runtime/krita/"):
    raise SystemExit("KRITA_BRIDGE_DIR must stay inside /app/runtime/krita")
print(data_dir)
print(bridge_dir)
PY
)

data_dir="${settings[0]}"
container_bridge="${settings[1]}"
host_bridge="$data_dir/runtime/krita${container_bridge#/app/runtime/krita}"
mkdir -p "$host_bridge"/{sources,requests,responses,outputs,previews,assets}

smoke_id="server-smoke-$(date -u +%Y%m%dT%H%M%SZ)-$$"
export VELVET_KRITA_SMOKE_ID="$smoke_id"
export VELVET_KRITA_HOST_BRIDGE="$host_bridge"
export VELVET_KRITA_CONTAINER_BRIDGE="$container_bridge"

python3 <<'PY'
from __future__ import annotations

import json
import os
import struct
import zlib
from pathlib import Path

smoke_id = os.environ["VELVET_KRITA_SMOKE_ID"]
host = Path(os.environ["VELVET_KRITA_HOST_BRIDGE"])
container = os.environ["VELVET_KRITA_CONTAINER_BRIDGE"].rstrip("/")


def chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


width = height = 256
rows = b"".join(b"\x00" + bytes((55, 65, 80, 255)) * width for _ in range(height))
png = (
    b"\x89PNG\r\n\x1a\n"
    + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    + chunk(b"IDAT", zlib.compress(rows, 9))
    + chunk(b"IEND", b"")
)

source_name = f"{smoke_id}.png"
response_name = f"{smoke_id}.json"
output_name = f"{smoke_id}.png"
(host / "sources" / source_name).write_bytes(png)
request = {
    "schema_version": 2,
    "request_id": smoke_id,
    "job_id": smoke_id,
    "revision": 1,
    "bridge_root": container,
    "source_path": f"{container}/sources/{source_name}",
    "response_path": f"{container}/responses/{response_name}",
    "output_path": f"{container}/outputs/{output_name}",
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
request_path = host / "requests" / f"{smoke_id}.json"
temporary = request_path.with_suffix(".tmp")
temporary.write_text(json.dumps(request, ensure_ascii=False, indent=2), encoding="utf-8")
temporary.replace(request_path)
PY

response="$host_bridge/responses/$smoke_id.json"
output="$host_bridge/outputs/$smoke_id.png"
request="$host_bridge/requests/$smoke_id.json"
processing="$host_bridge/requests/$smoke_id.processing"
source="$host_bridge/sources/$smoke_id.png"

deadline=$((SECONDS + TIMEOUT_SECONDS))
while (( SECONDS < deadline )); do
  if [[ -f "$response" ]]; then
    break
  fi
  sleep 2
done

if [[ ! -f "$response" ]]; then
  echo "Krita smoke timed out after ${TIMEOUT_SECONDS}s" >&2
  exit 1
fi

python3 - "$response" "$output" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

response_path = Path(sys.argv[1])
output_path = Path(sys.argv[2])
payload = json.loads(response_path.read_text(encoding="utf-8"))
if payload.get("status") != "ok":
    raise SystemExit(f"Krita smoke failed: {payload.get('error') or payload}")
if not output_path.is_file():
    raise SystemExit(f"Krita smoke output is missing: {output_path}")
if not output_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
    raise SystemExit("Krita smoke output is not PNG")
print(f"Krita server smoke succeeded: {output_path}")
PY

rm -f "$request" "$processing" "$response" "$output" "$source"
