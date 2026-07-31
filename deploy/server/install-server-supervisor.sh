#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-.env.server}"
COMPOSE_FILE="${VELVET_COMPOSE_FILE:-docker-compose.server.yml}"
CLIENT_GROUP="${SERVER_SUPERVISOR_CLIENT_GROUP:-velvet-supervisor-client}"
CLIENT_UID="${SERVER_SUPERVISOR_CLIENT_UID:-10001}"
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

if ! getent group "$CLIENT_GROUP" >/dev/null; then
  groupadd --system "$CLIENT_GROUP"
fi
usermod -a -G "$CLIENT_GROUP" velvet
client_gid="$(getent group "$CLIENT_GROUP" | cut -d: -f3)"
if [[ ! "$client_gid" =~ ^[1-9][0-9]*$ ]]; then
  echo "Could not resolve numeric GID for $CLIENT_GROUP." >&2
  exit 2
fi

python3 - "$ENV_FILE" "$client_gid" "$CLIENT_UID" <<'PY'
from __future__ import annotations

import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
client_gid = sys.argv[2]
client_uid = sys.argv[3]
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
        f"{data_dir}/control/supervisor/velvet-server-supervisor.sock"
    ),
    "SERVER_SUPERVISOR_SOCKET": (
        "/run/velvet-supervisor/velvet-server-supervisor.sock"
    ),
    "SERVER_SUPERVISOR_CLIENT_UID": client_uid,
    "SERVER_SUPERVISOR_CLIENT_GID": client_gid,
    "SERVER_SUPERVISOR_SOCKET_MODE": "0660",
    "SERVER_SUPERVISOR_AUTH_FAILURE_LIMIT": "5",
    "SERVER_SUPERVISOR_AUTH_FAILURE_WINDOW_SECONDS": "60",
    "SERVER_SUPERVISOR_AUTH_FAILURE_COOLDOWN_SECONDS": "120",
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

control_dir="$data_dir/control/supervisor"
runtime_dir="$data_dir/runtime/supervisor"
docker_config="$data_dir/runtime/docker-config"
legacy_socket="$runtime_dir/velvet-server-supervisor.sock"
new_socket="$control_dir/velvet-server-supervisor.sock"

mkdir -p "$control_dir" "$runtime_dir" "$docker_config"
chown velvet:"$CLIENT_GROUP" "$control_dir"
chmod 0750 "$control_dir"
chown velvet:velvet "$runtime_dir" "$docker_config"
chmod 0755 "$runtime_dir"
chmod 0700 "$docker_config"

python3 scripts/server_preflight.py \
  --env-file "$ENV_FILE" \
  --hermes-env .env.hermes \
  --skip-host-tools

install -m 0644 "$SERVER_UNIT_SOURCE" "$SERVER_UNIT_TARGET"
install -m 0644 "$COMPOSE_UNIT_SOURCE" "$COMPOSE_UNIT_TARGET"
systemctl daemon-reload
systemctl stop velvet-server-supervisor.service >/dev/null 2>&1 || true
if [[ -S "$legacy_socket" ]]; then
  rm -f "$legacy_socket"
elif [[ -e "$legacy_socket" || -L "$legacy_socket" ]]; then
  echo "Refusing to delete unexpected legacy Supervisor path: $legacy_socket" >&2
  exit 3
fi
if [[ -e "$new_socket" || -L "$new_socket" ]]; then
  if [[ -S "$new_socket" ]]; then
    owner_uid="$(stat -c '%u' "$new_socket")"
    owner_gid="$(stat -c '%g' "$new_socket")"
    mode="$(stat -c '%a' "$new_socket")"
    velvet_uid="$(id -u velvet)"
    if [[ "$owner_uid" != "$velvet_uid" || "$owner_gid" != "$client_gid" || "$mode" != "660" ]]; then
      echo "Refusing unexpected stale Supervisor socket ownership/mode." >&2
      exit 3
    fi
    rm -f "$new_socket"
  else
    echo "Refusing to replace non-socket Supervisor control path: $new_socket" >&2
    exit 3
  fi
fi
systemctl enable velvet-server-supervisor.service
systemctl restart velvet-server-supervisor.service

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
  build --pull supervisor-proxy
if systemctl is-active --quiet velvet-compose.service; then
  systemctl reload velvet-compose.service
else
  systemctl enable --now velvet-compose.service
fi

python3 - "$new_socket" "$client_gid" <<'PY'
from __future__ import annotations

import socket
import stat
import sys
import time
from pathlib import Path

path = Path(sys.argv[1])
expected_gid = int(sys.argv[2])
deadline = time.monotonic() + 30
while time.monotonic() < deadline:
    if path.is_socket():
        value = path.lstat()
        mode = stat.S_IMODE(value.st_mode)
        if value.st_gid != expected_gid or mode != 0o660 or mode & 0o007:
            raise SystemExit(
                f"Unsafe Server Supervisor socket metadata: gid={value.st_gid} mode={mode:04o}"
            )
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(3)
            client.connect(str(path))
            client.sendall(
                b"GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
            )
            response = client.recv(4096)
        if b"200 OK" in response and b'"ok": true' in response:
            print("Server Supervisor Unix API is healthy and permission-confined.")
            break
    time.sleep(1)
else:
    raise SystemExit("Server Supervisor Unix API did not become healthy.")
PY

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" ps
systemctl --no-pager --full status velvet-server-supervisor.service
