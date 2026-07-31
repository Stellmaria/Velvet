#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-.env.server}"
COMPOSE_FILE="${VELVET_COMPOSE_FILE:-docker-compose.server.yml}"
SERVER_UNIT_SOURCE="$APP_DIR/deploy/systemd/velvet-server-supervisor.service"
SERVER_UNIT_TARGET="/etc/systemd/system/velvet-server-supervisor.service"
COMPOSE_UNIT_SOURCE="$APP_DIR/deploy/systemd/velvet-compose.service"
COMPOSE_UNIT_TARGET="/etc/systemd/system/velvet-compose.service"

cd "$APP_DIR"
for path in "$ENV_FILE" "$COMPOSE_FILE" "$SERVER_UNIT_SOURCE" "$COMPOSE_UNIT_SOURCE"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing required file: $path" >&2
    exit 2
  fi
done

python3 - "$ENV_FILE" <<'PY'
from __future__ import annotations

import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8").splitlines()
values: dict[str, str] = {}
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip()

data_dir = values.get("VELVET_DATA_DIR", "/srv/velvet/data").rstrip("/")
token = values.get("SUPERVISOR_TOKEN", "")
if len(token) < 24 or "replace_with" in token.casefold():
    token = secrets.token_urlsafe(48)

updates = {
    "SUPERVISOR_ENABLED": "true",
    "SUPERVISOR_TOKEN": token,
    "SUPERVISOR_BASE_URL": "http://supervisor-proxy:8765",
    "SUPERVISOR_CLIENT_TIMEOUT_SECONDS": "20",
    "SUPERVISOR_COMMAND_TIMEOUT_SECONDS": "1800",
    "SERVER_SUPERVISOR_SOCKET_HOST": (
        f"{data_dir}/runtime/supervisor/velvet-server-supervisor.sock"
    ),
    "SERVER_SUPERVISOR_SOCKET": (
        "/runtime/supervisor/velvet-server-supervisor.sock"
    ),
}
seen: set[str] = set()
result: list[str] = []
for line in lines:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in line:
        result.append(line)
        continue
    key = line.split("=", 1)[0].strip()
    if key in updates:
        result.append(f"{key}={updates[key]}")
        seen.add(key)
    else:
        result.append(line)

missing = [key for key in updates if key not in seen]
if missing:
    result.extend(
        [
            "",
            "# Server Supervisor: current Linux/VPS runtime.",
            "# velvet_supervisor remains the deprecated Windows runtime.",
        ]
    )
    result.extend(f"{key}={updates[key]}" for key in missing)
path.write_text("\n".join(result).rstrip() + "\n", encoding="utf-8")
PY
chmod 600 "$ENV_FILE"

data_dir="$(python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys
from scripts.server_preflight import parse_env_file

value = parse_env_file(Path(sys.argv[1])).get("VELVET_DATA_DIR", "").strip()
if not value:
    raise SystemExit("VELVET_DATA_DIR is missing")
print(value)
PY
)"

mkdir -p "$data_dir/runtime/supervisor"
chown velvet:velvet "$data_dir/runtime/supervisor"
chmod 0755 "$data_dir/runtime/supervisor"
install -m 0644 "$SERVER_UNIT_SOURCE" "$SERVER_UNIT_TARGET"
install -m 0644 "$COMPOSE_UNIT_SOURCE" "$COMPOSE_UNIT_TARGET"
systemctl daemon-reload
systemctl enable --now velvet-server-supervisor.service

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
  build --pull supervisor-proxy
if systemctl is-active --quiet velvet-compose.service; then
  systemctl reload velvet-compose.service
else
  systemctl enable --now velvet-compose.service
fi

python3 - "$data_dir/runtime/supervisor/velvet-server-supervisor.sock" <<'PY'
from __future__ import annotations

import socket
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    if path.is_socket():
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(str(path))
            client.sendall(
                b"GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
            )
            response = client.recv(4096)
        if b"200 OK" in response and b'"ok": true' in response:
            print("Server Supervisor Unix API is healthy.")
            break
    time.sleep(1)
else:
    raise SystemExit("Server Supervisor Unix API did not become healthy.")
PY

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
systemctl --no-pager --full status velvet-server-supervisor.service
