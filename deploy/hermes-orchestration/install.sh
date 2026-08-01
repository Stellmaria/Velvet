#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите installer через sudo." >&2
  exit 1
fi

VELVET_APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
VELVET_ENV_FILE="${VELVET_ENV_FILE:-$VELVET_APP_DIR/.env.server}"
VELVET_COMPOSE_FILE="${VELVET_COMPOSE_FILE:-$VELVET_APP_DIR/docker-compose.server.yml}"
HERMES_ENV_FILE="${HERMES_ENV_FILE:-$VELVET_APP_DIR/.env.hermes}"
SERVICE_USER="${HERMES_ORCHESTRATION_SERVICE_USER:-velvet}"
CODERS_ROOT="${HERMES_CODERS_ROOT:-/srv/hermes-coders}"
CODERS_SOURCE="$VELVET_APP_DIR/deploy/hermes-coders"
OPERATOR_SOURCE="$VELVET_APP_DIR/deploy/hermes-operator"
ORCHESTRATION_SOURCE="$VELVET_APP_DIR/deploy/hermes-orchestration"
CONTROL_ROOT="${HERMES_OPERATOR_CONTROL_ROOT:-/srv/hermes-operator-control}"
OPERATOR_ENV="$CONTROL_ROOT/operator.env"
CODER_ROUTER_ENV="$CONTROL_ROOT/coders.env"
INCIDENT_ENV="$CONTROL_ROOT/incident.env"
AGENT_CONTROL_NETWORK="${HERMES_AGENT_CONTROL_NETWORK:-hermes-agent-control}"
ROUTER_UNIT_SOURCE="$VELVET_APP_DIR/deploy/systemd/hermes-coder-router.service"
ROUTER_UNIT_TARGET="/etc/systemd/system/hermes-coder-router.service"
INCIDENT_UNIT_SOURCE="$VELVET_APP_DIR/deploy/systemd/velvet-hermes-incident-monitor.service"
INCIDENT_UNIT_TARGET="/etc/systemd/system/velvet-hermes-incident-monitor.service"

required=(
  "$VELVET_ENV_FILE"
  "$VELVET_COMPOSE_FILE"
  "$HERMES_ENV_FILE"
  "$CODERS_SOURCE/compose.yaml"
  "$CODERS_SOURCE/SOUL.velvet.md"
  "$CODERS_SOURCE/SOUL.max.md"
  "$CODERS_SOURCE/ensure_runtime_config.py"
  "$CODERS_SOURCE/preflight.py"
  "$OPERATOR_SOURCE/coder_router.py"
  "$OPERATOR_SOURCE/coderctl.py"
  "$OPERATOR_SOURCE/SOUL.operator.md"
  "$ORCHESTRATION_SOURCE/compose.yaml"
  "$VELVET_APP_DIR/scripts/hermes_incident_monitor.py"
  "$ROUTER_UNIT_SOURCE"
  "$INCIDENT_UNIT_SOURCE"
  "$OPERATOR_ENV"
  "$CODERS_ROOT/secrets/velvet.env"
  "$CODERS_ROOT/secrets/max.env"
)
for path in "${required[@]}"; do
  if [[ ! -f "$path" ]]; then
    echo "Отсутствует обязательный файл: $path" >&2
    exit 2
  fi
done
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "Не найден service user: $SERVICE_USER" >&2
  exit 2
fi

if ! docker network inspect "$AGENT_CONTROL_NETWORK" >/dev/null 2>&1; then
  docker network create --internal "$AGENT_CONTROL_NETWORK" >/dev/null
fi
if [[ "$(docker network inspect -f '{{.Internal}}' "$AGENT_CONTROL_NETWORK")" != "true" ]]; then
  echo "Сеть $AGENT_CONTROL_NETWORK должна быть internal." >&2
  exit 3
fi

python3 - \
  "$CODERS_ROOT/secrets/velvet.env" \
  "$CODERS_ROOT/secrets/max.env" \
  "$OPERATOR_ENV" \
  "$CODER_ROUTER_ENV" \
  "$HERMES_ENV_FILE" \
  "$VELVET_ENV_FILE" \
  "$INCIDENT_ENV" <<'PY'
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def ensure_key(path: Path) -> dict[str, str]:
    values = parse_env(path)
    key = values.get("API_SERVER_KEY", "")
    if len(key) < 24:
        key = secrets.token_urlsafe(48)
    result: list[str] = []
    replaced = False
    for raw in path.read_text(encoding="utf-8").splitlines():
        if raw.strip().startswith("API_SERVER_KEY="):
            result.append(f"API_SERVER_KEY={key}")
            replaced = True
        else:
            result.append(raw)
    if not replaced:
        if result and result[-1].strip():
            result.append("")
        result.extend(("# Internal Hermes Runs API", f"API_SERVER_KEY={key}"))
    path.write_text("\n".join(result).rstrip() + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    values["API_SERVER_KEY"] = key
    return values


velvet_path, max_path, operator_path, router_path, hermes_path, server_path, incident_path = map(
    Path, sys.argv[1:]
)
velvet = ensure_key(velvet_path)
maximum = ensure_key(max_path)
if velvet["API_SERVER_KEY"] == maximum["API_SERVER_KEY"]:
    new_key = secrets.token_urlsafe(48)
    lines = max_path.read_text(encoding="utf-8").splitlines()
    max_path.write_text(
        "\n".join(
            f"API_SERVER_KEY={new_key}" if line.strip().startswith("API_SERVER_KEY=") else line
            for line in lines
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    os.chmod(max_path, 0o600)
    maximum["API_SERVER_KEY"] = new_key

operator = parse_env(operator_path)
client_token = operator.get("HERMES_OPS_CLIENT_TOKEN", "")
if len(client_token) < 24:
    raise SystemExit("HERMES_OPS_CLIENT_TOKEN отсутствует или слишком короткий")
router_values = {
    "HERMES_CODER_ROUTER_CLIENT_TOKEN": client_token,
    "HERMES_CODER_VELVET_TOKEN": velvet["API_SERVER_KEY"],
    "HERMES_CODER_MAX_TOKEN": maximum["API_SERVER_KEY"],
    "HERMES_CODER_VELVET_BASE_URL": "http://hermes-coder-velvet:8642",
    "HERMES_CODER_MAX_BASE_URL": "http://hermes-coder-max:8642",
    "HERMES_CODER_ROUTER_HOST": "0.0.0.0",
    "HERMES_CODER_ROUTER_PORT": "8878",
    "HERMES_CODER_ROUTER_TIMEOUT_SECONDS": "30",
}
router_path.write_text(
    "\n".join(f"{name}={value}" for name, value in router_values.items()) + "\n",
    encoding="utf-8",
)
os.chmod(router_path, 0o600)

hermes = parse_env(hermes_path)
server = parse_env(server_path)
api_key = hermes.get("API_SERVER_KEY", "")
if len(api_key) < 24:
    raise SystemExit("API_SERVER_KEY основного Hermes отсутствует или слишком короткий")
port = server.get("HERMES_LOOPBACK_PORT", "8642")
if not port.isdigit() or not 1024 <= int(port) <= 65535:
    raise SystemExit("HERMES_LOOPBACK_PORT должен быть корректным TCP port")
incident_values = {
    "HERMES_INCIDENT_ENABLED": "true",
    "HERMES_BASE_URL": f"http://127.0.0.1:{port}",
    "HERMES_API_KEY": api_key,
    "HERMES_INCIDENT_POLL_SECONDS": server.get("HERMES_INCIDENT_POLL_SECONDS", "30"),
    "HERMES_INCIDENT_UNHEALTHY_POLLS": server.get("HERMES_INCIDENT_UNHEALTHY_POLLS", "2"),
    "HERMES_INCIDENT_LOG_LINES": server.get("HERMES_INCIDENT_LOG_LINES", "200"),
    "HERMES_INCIDENT_RUN_POLL_SECONDS": server.get(
        "HERMES_INCIDENT_RUN_POLL_SECONDS", "5"
    ),
    "HERMES_INCIDENT_RUN_TIMEOUT_SECONDS": server.get(
        "HERMES_INCIDENT_RUN_TIMEOUT_SECONDS", "3600"
    ),
    "HERMES_INCIDENT_COOLDOWN_SECONDS": server.get(
        "HERMES_INCIDENT_COOLDOWN_SECONDS", "600"
    ),
}
incident_path.write_text(
    "\n".join(f"{name}={value}" for name, value in incident_values.items()) + "\n",
    encoding="utf-8",
)
os.chmod(incident_path, 0o600)
print("Orchestration credentials prepared without printing secret values.")
PY

chown "$SERVICE_USER:$SERVICE_USER" \
  "$CODERS_ROOT/secrets/velvet.env" \
  "$CODERS_ROOT/secrets/max.env" \
  "$CODER_ROUTER_ENV" \
  "$INCIDENT_ENV"
chmod 0600 \
  "$CODERS_ROOT/secrets/velvet.env" \
  "$CODERS_ROOT/secrets/max.env" \
  "$CODER_ROUTER_ENV" \
  "$INCIDENT_ENV"

python3 \
  "$CODERS_SOURCE/ensure_runtime_config.py" \
  "$CODERS_ROOT/data/velvet/config.yaml" \
  "$CODERS_ROOT/data/max/config.yaml"
env HERMES_CODERS_ROOT="$CODERS_ROOT" python3 "$CODERS_SOURCE/preflight.py"

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
install -d -m 0750 "$hermes_data" "$hermes_data/tools" "$hermes_data/orchestration"
hermes_uid="$(stat -c '%u' "$hermes_data")"
hermes_gid="$(stat -c '%g' "$hermes_data")"
install -m 0500 -o "$hermes_uid" -g "$hermes_gid" \
  "$OPERATOR_SOURCE/coderctl.py" "$hermes_data/tools/coderctl.py"
chown "$hermes_uid:$hermes_gid" "$hermes_data/orchestration"
chmod 0750 "$hermes_data/orchestration"

python3 - "$hermes_data/SOUL.md" "$OPERATOR_SOURCE/SOUL.operator.md" <<'PY'
from pathlib import Path
import sys

begin = "<!-- BEGIN MANAGED HERMES OPERATOR CONTROL -->"
end = "<!-- END MANAGED HERMES OPERATOR CONTROL -->"
target = Path(sys.argv[1])
managed = Path(sys.argv[2]).read_text(encoding="utf-8").strip()
current = target.read_text(encoding="utf-8") if target.exists() else "# Hermes operator\n"
block = f"{begin}\n{managed}\n{end}"
if begin in current and end in current:
    prefix, rest = current.split(begin, 1)
    _, suffix = rest.split(end, 1)
    current = prefix.rstrip() + "\n\n" + block + suffix
else:
    current = current.rstrip() + "\n\n" + block + "\n"
target.write_text(current, encoding="utf-8")
PY
chown "$hermes_uid:$hermes_gid" "$hermes_data/SOUL.md"
chmod 0640 "$hermes_data/SOUL.md"

for project in velvet max; do
  data_dir="$CODERS_ROOT/data/$project"
  if [[ ! -d "$data_dir" ]]; then
    echo "Отсутствует coder data directory: $data_dir" >&2
    exit 4
  fi
  install -m 0640 \
    -o "$(stat -c '%u' "$data_dir")" \
    -g "$(stat -c '%g' "$data_dir")" \
    "$CODERS_SOURCE/SOUL.$project.md" "$data_dir/SOUL.md"
done

runuser -u "$SERVICE_USER" -- env \
  HERMES_CODERS_ROOT="$CODERS_ROOT" \
  HERMES_AGENT_CONTROL_NETWORK="$AGENT_CONTROL_NETWORK" \
  docker compose --profile velvet --profile max -f "$CODERS_SOURCE/compose.yaml" \
  up -d --build --force-recreate

install -m 0644 "$ROUTER_UNIT_SOURCE" "$ROUTER_UNIT_TARGET"
install -m 0644 "$INCIDENT_UNIT_SOURCE" "$INCIDENT_UNIT_TARGET"
systemctl daemon-reload
systemctl enable --now hermes-coder-router.service

runuser -u "$SERVICE_USER" -- bash -ceu "
  cd '$VELVET_APP_DIR'
  docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
    --profile agent up -d hermes
  docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
    --profile agent restart hermes
"

main_hermes_healthy=false
for _ in $(seq 1 45); do
  if python3 - "$INCIDENT_ENV" <<'PY' >/dev/null 2>&1
from pathlib import Path
import json
import sys
import urllib.request

values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if "=" in raw:
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip()
payload = json.load(urllib.request.urlopen(values["HERMES_BASE_URL"] + "/health", timeout=3))
raise SystemExit(0 if payload.get("status") == "ok" else 1)
PY
  then
    main_hermes_healthy=true
    break
  fi
  sleep 2
done
if [[ "$main_hermes_healthy" != "true" ]]; then
  echo "Основной Hermes API не достиг healthy status." >&2
  exit 5
fi

coder_health_ok=false
for _ in $(seq 1 30); do
  if runuser -u "$SERVICE_USER" -- \
    docker compose --env-file "$VELVET_ENV_FILE" -f "$VELVET_COMPOSE_FILE" \
      --profile agent exec -T hermes \
      python /opt/data/tools/coderctl.py health all >/dev/null 2>&1; then
    coder_health_ok=true
    break
  fi
  sleep 2
done
if [[ "$coder_health_ok" != "true" ]]; then
  systemctl --no-pager --full status hermes-coder-router.service >&2 || true
  journalctl -u hermes-coder-router.service -n 100 --no-pager >&2 || true
  echo "Main Hermes не смог получить capabilities обоих coder-агентов." >&2
  exit 6
fi

systemctl enable --now velvet-hermes-incident-monitor.service
if ! systemctl is-active --quiet velvet-hermes-incident-monitor.service; then
  systemctl --no-pager --full status velvet-hermes-incident-monitor.service >&2 || true
  exit 7
fi

systemctl --no-pager --full status hermes-coder-router.service
systemctl --no-pager --full status velvet-hermes-incident-monitor.service
runuser -u "$SERVICE_USER" -- env \
  HERMES_CODERS_ROOT="$CODERS_ROOT" \
  HERMES_AGENT_CONTROL_NETWORK="$AGENT_CONTROL_NETWORK" \
  docker compose --profile velvet --profile max -f "$CODERS_SOURCE/compose.yaml" ps
runuser -u "$SERVICE_USER" -- env \
  HERMES_CODER_ROUTER_ENV_FILE="$CODER_ROUTER_ENV" \
  HERMES_AGENT_CONTROL_NETWORK="$AGENT_CONTROL_NETWORK" \
  docker compose -f "$ORCHESTRATION_SOURCE/compose.yaml" ps

printf '%s\n' \
  "Hermes coder orchestration installed." \
  "Main Hermes can submit/status/wait/list tasks through /opt/data/tools/coderctl.py." \
  "Both coder capabilities were verified through the isolated router." \
  "Read-only Velvet incident monitor is active and reports terminal results to Telegram."
