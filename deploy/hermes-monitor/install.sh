#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите installer через sudo." >&2
  exit 1
fi

VELVET_APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
VELVET_ENV_FILE="${VELVET_ENV_FILE:-$VELVET_APP_DIR/.env.server}"
VELVET_COMPOSE_FILE="${VELVET_COMPOSE_FILE:-$VELVET_APP_DIR/docker-compose.server.yml}"
OPERATOR_ENV="${HERMES_OPERATOR_ENV:-/srv/hermes-operator-control/operator.env}"
SERVICE_USER="${HERMES_MONITOR_SERVICE_USER:-velvet}"
SOURCE_DIR="$VELVET_APP_DIR/deploy/hermes-monitor"
HOST_SCRIPT_TARGET="/usr/local/libexec/velvet-hermes-operator-monitor.py"
HOST_UNIT_SOURCE="$VELVET_APP_DIR/deploy/systemd/hermes-operator-monitor.service"
HOST_UNIT_TARGET="/etc/systemd/system/hermes-operator-monitor.service"
GATEWAY_UNIT_SOURCE="$VELVET_APP_DIR/deploy/systemd/hermes-monitor-gateway.service"
GATEWAY_UNIT_TARGET="/etc/systemd/system/hermes-monitor-gateway.service"
SOCKET_PATH="/run/hermes-operator-monitor/monitor.sock"

for path in \
  "$VELVET_ENV_FILE" \
  "$VELVET_COMPOSE_FILE" \
  "$OPERATOR_ENV" \
  "$SOURCE_DIR/compose.yaml" \
  "$SOURCE_DIR/Dockerfile" \
  "$SOURCE_DIR/gateway.py" \
  "$SOURCE_DIR/host_monitor.py" \
  "$SOURCE_DIR/monitorctl.py" \
  "$HOST_UNIT_SOURCE" \
  "$GATEWAY_UNIT_SOURCE" \
  "$VELVET_APP_DIR/deploy/hermes-operator/AGENTS.kael.md"
do
  if [[ ! -f "$path" ]]; then
    echo "Отсутствует обязательный файл: $path" >&2
    exit 2
  fi
done

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "Не найден service user: $SERVICE_USER" >&2
  exit 2
fi

python3 - "$OPERATOR_ENV" <<'PY'
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8-sig").splitlines()
values: dict[str, str] = {}
for raw in lines:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

if len(values.get("HERMES_OPS_CLIENT_TOKEN", "")) < 24:
    raise SystemExit("HERMES_OPS_CLIENT_TOKEN отсутствует или слишком короткий")
if not values.get("HERMES_OPS_SOCKET_GID", "").isdigit():
    raise SystemExit("HERMES_OPS_SOCKET_GID отсутствует или некорректен")

token = values.get("HERMES_OPS_MONITOR_TOKEN", "")
if len(token) < 24:
    token = secrets.token_urlsafe(48)

updates = {
    "HERMES_OPS_MONITOR_TOKEN": token,
    "HERMES_OPS_MONITOR_SOCKET": "/run/hermes-operator-monitor/monitor.sock",
    "HERMES_OPS_MONITOR_RUNTIME_DIR": "/run/hermes-operator-monitor",
    "HERMES_OPS_MONITOR_TIMEOUT_SECONDS": "12",
    "HERMES_OPS_MONITOR_REQUEST_TIMEOUT_SECONDS": "20",
    "HERMES_MONITOR_GATEWAY_HOST": "0.0.0.0",
    "HERMES_MONITOR_GATEWAY_PORT": "8879",
}
result: list[str] = []
seen: set[str] = set()
for raw in lines:
    if "=" in raw:
        name = raw.split("=", 1)[0].strip()
        if name in updates:
            if name not in seen:
                result.append(f"{name}={updates[name]}")
                seen.add(name)
            continue
    result.append(raw)
if result and result[-1].strip():
    result.append("")
for name, value in updates.items():
    if name not in seen:
        result.append(f"{name}={value}")
path.write_text("\n".join(result).rstrip() + "\n", encoding="utf-8")
os.chmod(path, 0o600)
print("Hermes monitor credentials prepared without printing secret values.")
PY
chown "$SERVICE_USER:$SERVICE_USER" "$OPERATOR_ENV"
chmod 0600 "$OPERATOR_ENV"

install -d -m 0755 /usr/local/libexec
install -m 0755 -o root -g root "$SOURCE_DIR/host_monitor.py" "$HOST_SCRIPT_TARGET"
install -m 0644 -o root -g root "$HOST_UNIT_SOURCE" "$HOST_UNIT_TARGET"
install -m 0644 -o root -g root "$GATEWAY_UNIT_SOURCE" "$GATEWAY_UNIT_TARGET"

velvet_data_dir="$(python3 - "$VELVET_ENV_FILE" <<'PY'
from pathlib import Path
import sys

values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")
print(values.get("VELVET_DATA_DIR", "/srv/velvet/data"))
PY
)"
hermes_data="$velvet_data_dir/hermes"
if [[ ! -d "$hermes_data" ]]; then
  echo "Отсутствует data directory основного Hermes: $hermes_data" >&2
  exit 3
fi
hermes_uid="$(stat -c '%u' "$hermes_data")"
hermes_gid="$(stat -c '%g' "$hermes_data")"
install -d -m 0750 -o "$hermes_uid" -g "$hermes_gid" "$hermes_data/tools"
install -m 0500 -o "$hermes_uid" -g "$hermes_gid" \
  "$SOURCE_DIR/monitorctl.py" "$hermes_data/tools/monitorctl.py"
install -m 0640 -o "$hermes_uid" -g "$hermes_gid" \
  "$VELVET_APP_DIR/deploy/hermes-operator/AGENTS.kael.md" "$hermes_data/AGENTS.md"

systemctl daemon-reload
systemctl enable hermes-operator-monitor.service hermes-monitor-gateway.service
systemctl restart hermes-operator-monitor.service
for _ in $(seq 1 30); do
  [[ -S "$SOCKET_PATH" ]] && break
  sleep 1
done
if [[ ! -S "$SOCKET_PATH" ]]; then
  systemctl --no-pager --full status hermes-operator-monitor.service >&2 || true
  echo "Hermes monitor host bridge did not create its socket." >&2
  exit 4
fi
systemctl restart hermes-monitor-gateway.service

runuser -u "$SERVICE_USER" -- bash -ceu "
  cd '$VELVET_APP_DIR'
  docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
    --profile agent up -d hermes
  docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
    --profile agent restart hermes
"

healthy=false
for _ in $(seq 1 45); do
  if runuser -u "$SERVICE_USER" -- \
    docker compose --env-file "$VELVET_ENV_FILE" -f "$VELVET_COMPOSE_FILE" \
      --profile agent exec -T hermes \
      python /opt/data/tools/monitorctl.py summary >/dev/null 2>&1; then
    healthy=true
    break
  fi
  sleep 2
done
if [[ "$healthy" != "true" ]]; then
  systemctl --no-pager --full status hermes-operator-monitor.service >&2 || true
  systemctl --no-pager --full status hermes-monitor-gateway.service >&2 || true
  echo "Hermes monitor summary did not become reachable from Kael." >&2
  exit 5
fi

runuser -u "$SERVICE_USER" -- \
  docker compose --env-file "$VELVET_ENV_FILE" -f "$VELVET_COMPOSE_FILE" \
    --profile agent exec -T hermes \
    sh -ceu '
      test "$(id -u)" = "10000"
      test -x /opt/data/tools/monitorctl.py
      python /opt/data/tools/monitorctl.py --help >/dev/null
    '

systemctl --no-pager --full status hermes-operator-monitor.service
systemctl --no-pager --full status hermes-monitor-gateway.service

printf '%s\n' \
  "Hermes read-only monitor installed." \
  "Kael can inspect only fixed views: summary, resources, containers, services, gpu, models, processes and incidents." \
  "The gateway accepts GET only and exposes no arbitrary commands, paths, unit names, container names or process command lines."
