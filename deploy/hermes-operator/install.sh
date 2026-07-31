#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите installer через sudo." >&2
  exit 1
fi

VELVET_APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
VELVET_ENV_FILE="${VELVET_ENV_FILE:-$VELVET_APP_DIR/.env.server}"
VELVET_COMPOSE_FILE="${VELVET_COMPOSE_FILE:-$VELVET_APP_DIR/docker-compose.server.yml}"
ROMATIC_APP_DIR="${ROMATIC_APP_DIR:-/srv/romatic-club-max}"
ROMATIC_ENV_FILE="${ROMATIC_ENV_FILE:-$ROMATIC_APP_DIR/.env}"
ROMATIC_COMPOSE_FILE="${ROMATIC_COMPOSE_FILE:-$ROMATIC_APP_DIR/compose.yaml}"
SERVICE_USER="${HERMES_OPERATOR_SERVICE_USER:-velvet}"
CONTROL_ROOT="${HERMES_OPERATOR_CONTROL_ROOT:-/srv/hermes-operator-control}"
CONTROL_ENV="$CONTROL_ROOT/operator.env"
CONTROL_NETWORK="${HERMES_SUPERVISOR_NETWORK:-hermes-supervisor-control}"
VELVET_BACKEND_NETWORK="${VELVET_BACKEND_NETWORK:-velvet_backend}"
SOURCE_DIR="$VELVET_APP_DIR/deploy/hermes-operator"
UNIT_SOURCE="$VELVET_APP_DIR/deploy/systemd/hermes-operator-control.service"
UNIT_TARGET="/etc/systemd/system/hermes-operator-control.service"

for path in \
  "$VELVET_ENV_FILE" \
  "$VELVET_COMPOSE_FILE" \
  "$ROMATIC_ENV_FILE" \
  "$ROMATIC_COMPOSE_FILE" \
  "$SOURCE_DIR/compose.yaml" \
  "$SOURCE_DIR/gateway.py" \
  "$SOURCE_DIR/opsctl.py" \
  "$SOURCE_DIR/SOUL.operator.md" \
  "$UNIT_SOURCE"; do
  if [[ ! -f "$path" ]]; then
    echo "Отсутствует обязательный файл: $path" >&2
    exit 2
  fi
done

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "Не найден service user: $SERVICE_USER" >&2
  exit 2
fi
if ! grep -q "hermes-supervisor-control" "$ROMATIC_COMPOSE_FILE"; then
  echo "Romatic compose ещё не содержит безопасную control network." >&2
  echo "Сначала обновите Stellmaria/romatic_club_bot_max до совместимого commit." >&2
  exit 3
fi
if ! docker network inspect "$VELVET_BACKEND_NETWORK" >/dev/null 2>&1; then
  echo "Не найдена production-сеть Velvet: $VELVET_BACKEND_NETWORK" >&2
  exit 3
fi

install -d -m 0750 -o "$SERVICE_USER" -g "$SERVICE_USER" "$CONTROL_ROOT"

python3 - \
  "$VELVET_ENV_FILE" \
  "$ROMATIC_ENV_FILE" \
  "$CONTROL_ENV" <<'PY'
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


velvet = parse_env(Path(sys.argv[1]))
romatic = parse_env(Path(sys.argv[2]))
target = Path(sys.argv[3])
existing = parse_env(target) if target.exists() else {}

velvet_token = velvet.get("SUPERVISOR_TOKEN", "")
romatic_token = romatic.get("SUPERVISOR_TOKEN", "")
for name, value in (
    ("Velvet SUPERVISOR_TOKEN", velvet_token),
    ("Romatic SUPERVISOR_TOKEN", romatic_token),
):
    if len(value) < 24:
        raise SystemExit(f"{name} is missing or too short")

client_token = existing.get("HERMES_OPS_CLIENT_TOKEN", "")
if len(client_token) < 24:
    client_token = secrets.token_urlsafe(48)

values = {
    "HERMES_OPS_CLIENT_TOKEN": client_token,
    "VELVET_SUPERVISOR_TOKEN": velvet_token,
    "ROMATIC_SUPERVISOR_TOKEN": romatic_token,
    "VELVET_SUPERVISOR_BASE_URL": "http://supervisor-proxy:8765",
    "ROMATIC_SUPERVISOR_BASE_URL": "http://romatic-supervisor:8765",
    "HERMES_OPS_GATEWAY_HOST": "0.0.0.0",
    "HERMES_OPS_GATEWAY_PORT": "8877",
    "HERMES_OPS_UPSTREAM_TIMEOUT_SECONDS": "30",
}
target.write_text(
    "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
    encoding="utf-8",
)
os.chmod(target, 0o600)
print("Operator credentials prepared without printing secret values.")
PY
chown "$SERVICE_USER:$SERVICE_USER" "$CONTROL_ENV"
chmod 0600 "$CONTROL_ENV"

velvet_data_dir="$(python3 - "$VELVET_ENV_FILE" <<'PY'
from pathlib import Path
import sys

values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")
print(values.get("VELVET_DATA_DIR", "/srv/velvet/data"))
PY
)"
hermes_data="$velvet_data_dir/hermes"
install -d -m 0750 "$hermes_data" "$hermes_data/tools"
hermes_uid="$(stat -c '%u' "$hermes_data")"
hermes_gid="$(stat -c '%g' "$hermes_data")"
install -m 0500 -o "$hermes_uid" -g "$hermes_gid" \
  "$SOURCE_DIR/opsctl.py" "$hermes_data/tools/opsctl.py"

python3 - "$CONTROL_ENV" "$hermes_data/.hermes-ops-client-token" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    result = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip()
    return result

source = parse_env(Path(sys.argv[1]))
target = Path(sys.argv[2])
target.write_text(source["HERMES_OPS_CLIENT_TOKEN"] + "\n", encoding="utf-8")
os.chmod(target, 0o600)
PY
chown "$hermes_uid:$hermes_gid" "$hermes_data/.hermes-ops-client-token"
chmod 0600 "$hermes_data/.hermes-ops-client-token"

python3 - \
  "$hermes_data/SOUL.md" \
  "$SOURCE_DIR/SOUL.operator.md" <<'PY'
from __future__ import annotations

import sys
from pathlib import Path

BEGIN = "<!-- BEGIN MANAGED HERMES OPERATOR CONTROL -->"
END = "<!-- END MANAGED HERMES OPERATOR CONTROL -->"
target = Path(sys.argv[1])
managed = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
current = target.read_text(encoding="utf-8") if target.exists() else "# Hermes operator\n"
block = f"{BEGIN}\n{managed}\n{END}"
if BEGIN in current and END in current:
    prefix, rest = current.split(BEGIN, 1)
    _, suffix = rest.split(END, 1)
    current = prefix.rstrip() + "\n\n" + block + suffix
else:
    current = current.rstrip() + "\n\n" + block + "\n"
target.write_text(current, encoding="utf-8")
PY
chown "$hermes_uid:$hermes_gid" "$hermes_data/SOUL.md"
chmod 0640 "$hermes_data/SOUL.md"

romatic_data_dir="$(python3 - "$ROMATIC_ENV_FILE" "$ROMATIC_APP_DIR" <<'PY'
from pathlib import Path
import sys

values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")
print(values.get("ROMATIC_DATA_DIR", str(Path(sys.argv[2]) / "server-data")))
PY
)"
install -d -m 0700 -o "$SERVICE_USER" -g "$SERVICE_USER" \
  "$romatic_data_dir/runtime/docker-config"
runuser -u "$SERVICE_USER" -- env \
  DOCKER_CONFIG="$romatic_data_dir/runtime/docker-config" \
  COMPOSE_BAKE=false \
  HERMES_SUPERVISOR_NETWORK="$CONTROL_NETWORK" \
  docker compose \
    --env-file "$ROMATIC_ENV_FILE" \
    -f "$ROMATIC_COMPOSE_FILE" \
    up -d --force-recreate supervisor-proxy

if ! docker network inspect "$CONTROL_NETWORK" >/dev/null 2>&1; then
  echo "Romatic Compose не создал control network: $CONTROL_NETWORK" >&2
  exit 4
fi
if [[ "$(docker network inspect -f '{{.Internal}}' "$CONTROL_NETWORK")" != "true" ]]; then
  echo "Control network должна быть internal: $CONTROL_NETWORK" >&2
  exit 4
fi

install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
systemctl daemon-reload
systemctl enable hermes-operator-control.service
systemctl restart hermes-operator-control.service

if [[ -f "$VELVET_APP_DIR/.env.hermes" ]]; then
  runuser -u "$SERVICE_USER" -- bash -ceu "
    cd '$VELVET_APP_DIR'
    docker compose \
      --env-file '$VELVET_ENV_FILE' \
      -f '$VELVET_COMPOSE_FILE' \
      --profile agent \
      up -d hermes
    docker compose \
      --env-file '$VELVET_ENV_FILE' \
      -f '$VELVET_COMPOSE_FILE' \
      --profile agent \
      restart hermes
  "
else
  echo "ПРЕДУПРЕЖДЕНИЕ: .env.hermes отсутствует; gateway установлен, основной Hermes не запущен." >&2
fi

runuser -u "$SERVICE_USER" -- env \
  HERMES_OPS_ENV_FILE="$CONTROL_ENV" \
  HERMES_SUPERVISOR_NETWORK="$CONTROL_NETWORK" \
  VELVET_BACKEND_NETWORK="$VELVET_BACKEND_NETWORK" \
  docker compose -f "$SOURCE_DIR/compose.yaml" ps
systemctl --no-pager --full status hermes-operator-control.service

echo
printf '%s\n' \
  "Hermes operator control installed." \
  "@VelvetHermesBot: status/logs/start/restart/update/rollback через /opt/data/tools/opsctl.py." \
  "Coder bots remain isolated from Docker, systemd, production env and this control gateway."
