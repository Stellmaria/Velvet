#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите launcher installer через sudo." >&2
  exit 1
fi

SOURCE_DIR="${HERMES_SANDBOX_SOURCE_DIR:-/srv/velvet/deploy/hermes-sandbox-launcher}"
CODERS_SOURCE="${HERMES_CODERS_SOURCE_DIR:-/srv/velvet/deploy/hermes-coders}"
INSTALL_DIR="${HERMES_SANDBOX_INSTALL_DIR:-/usr/local/lib/hermes-sandbox-launcher}"
ROOT="${HERMES_CODERS_ROOT:-/srv/hermes-coders}"
APP_GROUP="${HERMES_CODERS_APP_GROUP:-velvet}"
SANDBOX_GROUP="${HERMES_SANDBOX_GROUP:-hermes-sandbox}"
NETWORK="${HERMES_SANDBOX_NETWORK:-hermes-sandbox-egress}"
HERMES_UID_VALUE="${HERMES_UID:-10000}"
HERMES_GID_VALUE="${HERMES_GID:-10000}"
SOCKET_SOURCE="/srv/velvet/deploy/systemd/hermes-sandbox-launcher.socket"
SERVICE_SOURCE="/srv/velvet/deploy/systemd/hermes-sandbox-launcher.service"
SOCKET_TARGET="/etc/systemd/system/hermes-sandbox-launcher.socket"
SERVICE_TARGET="/etc/systemd/system/hermes-sandbox-launcher.service"
RUNNER_PROFILE_SOURCE="$CODERS_SOURCE/security/apparmor-hermes-codex-runner"
RUN_PROFILE_SOURCE="$CODERS_SOURCE/security/apparmor-hermes-codex-run"
RUNNER_PROFILE_TARGET="/etc/apparmor.d/hermes-codex-runner"
RUN_PROFILE_TARGET="/etc/apparmor.d/hermes-codex-run"

if [[ ! "$NETWORK" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$ ]]; then
  echo "Небезопасное имя HERMES_SANDBOX_NETWORK: $NETWORK" >&2
  exit 2
fi

for required in \
  "$SOURCE_DIR/launcher.py" \
  "$SOURCE_DIR/launcher_contract.py" \
  "$SOURCE_DIR/launcher_runtime.py" \
  "$CODERS_SOURCE/sandbox_entrypoint.py" \
  "$SOCKET_SOURCE" \
  "$SERVICE_SOURCE" \
  "$RUNNER_PROFILE_SOURCE" \
  "$RUN_PROFILE_SOURCE"; do
  if [[ ! -f "$required" ]]; then
    echo "Отсутствует launcher artifact: $required" >&2
    exit 2
  fi
done

if [[ "$(cat /sys/module/apparmor/parameters/enabled 2>/dev/null)" != "Y" ]]; then
  echo "AppArmor не включён; launcher installation остановлена" >&2
  exit 3
fi

docker info >/dev/null
if ! getent group "$SANDBOX_GROUP" >/dev/null; then
  groupadd --system "$SANDBOX_GROUP"
fi
SANDBOX_GID_VALUE="$(getent group "$SANDBOX_GROUP" | cut -d: -f3)"
if [[ ! "$SANDBOX_GID_VALUE" =~ ^[0-9]+$ ]]; then
  echo "Не удалось определить GID группы $SANDBOX_GROUP" >&2
  exit 3
fi

install -d -o root -g root -m 0755 "$INSTALL_DIR"
install -o root -g root -m 0555 "$SOURCE_DIR/launcher.py" "$INSTALL_DIR/launcher.py"
install -o root -g root -m 0444 \
  "$SOURCE_DIR/launcher_contract.py" \
  "$INSTALL_DIR/launcher_contract.py"
install -o root -g root -m 0444 \
  "$SOURCE_DIR/launcher_runtime.py" \
  "$INSTALL_DIR/launcher_runtime.py"
install -o root -g root -m 0555 \
  "$CODERS_SOURCE/sandbox_entrypoint.py" \
  "$INSTALL_DIR/sandbox_entrypoint.py"

install -d -o "$HERMES_UID_VALUE" -g "$HERMES_GID_VALUE" -m 0750 \
  "$ROOT/codex-runs" \
  "$ROOT/codex-runs/velvet" \
  "$ROOT/codex-runs/max" \
  "$ROOT/codex-runs/velvet/workspaces" \
  "$ROOT/codex-runs/max/workspaces" \
  "$ROOT/codex-runs/velvet/probes" \
  "$ROOT/codex-runs/max/probes"

install -d -o root -g "$APP_GROUP" -m 0750 "$ROOT"
temp_env="$(mktemp "$ROOT/.launcher.env.XXXXXX")"
trap 'rm -f -- "$temp_env"' EXIT
cat > "$temp_env" <<EOF
HERMES_SANDBOX_GID=$SANDBOX_GID_VALUE
HERMES_SANDBOX_NETWORK=$NETWORK
HERMES_SANDBOX_INSTALL_DIR=$INSTALL_DIR
HERMES_UID=$HERMES_UID_VALUE
HERMES_GID=$HERMES_GID_VALUE
EOF
chown root:"$APP_GROUP" "$temp_env"
chmod 0640 "$temp_env"
mv -f "$temp_env" "$ROOT/launcher.env"
trap - EXIT

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  docker network create --driver bridge --attachable "$NETWORK" >/dev/null
fi

install -o root -g root -m 0644 "$RUNNER_PROFILE_SOURCE" "$RUNNER_PROFILE_TARGET"
install -o root -g root -m 0644 "$RUN_PROFILE_SOURCE" "$RUN_PROFILE_TARGET"
apparmor_parser -r "$RUNNER_PROFILE_TARGET"
apparmor_parser -r "$RUN_PROFILE_TARGET"
install -o root -g root -m 0644 "$SOCKET_SOURCE" "$SOCKET_TARGET"
install -o root -g root -m 0644 "$SERVICE_SOURCE" "$SERVICE_TARGET"

systemctl daemon-reload
systemctl enable --now hermes-sandbox-launcher.socket
systemctl try-restart hermes-sandbox-launcher.service || true

python3 - "$NETWORK" <<'PY'
import json
import socket
import sys

expected_network = sys.argv[1]
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(10)
    client.connect('/run/hermes-sandbox/launcher.sock')
    client.sendall(b'{"action":"ping"}\n')
    raw = b''
    while b'\n' not in raw:
        chunk = client.recv(65536)
        if not chunk:
            break
        raw += chunk
response = json.loads(raw.split(b'\n', 1)[0].decode('utf-8'))
if response.get('ok') is not True:
    raise SystemExit('launcher ping rejected')
if response.get('backend') != 'host-docker-launcher':
    raise SystemExit('unexpected launcher backend')
if response.get('nested_bwrap') is not False:
    raise SystemExit('launcher still reports nested bwrap')
if response.get('network') != expected_network:
    raise SystemExit('launcher network mismatch')
PY

printf '%s\n' \
  "Hermes sandbox launcher installed." \
  "- socket: /run/hermes-sandbox/launcher.sock" \
  "- network: $NETWORK" \
  "- code: $INSTALL_DIR" \
  "- coder traffic was not switched by this installer"
