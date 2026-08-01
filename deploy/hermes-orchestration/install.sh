#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите installer через sudo." >&2
  exit 1
fi

VELVET_APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
VELVET_ENV_FILE="${VELVET_ENV_FILE:-$VELVET_APP_DIR/.env.server}"
VELVET_COMPOSE_FILE="${VELVET_COMPOSE_FILE:-$VELVET_APP_DIR/docker-compose.server.yml}"
SERVICE_USER="${HERMES_ORCHESTRATION_SERVICE_USER:-velvet}"
CODERS_ROOT="${HERMES_CODERS_ROOT:-/srv/hermes-coders}"
CODERS_SOURCE="$VELVET_APP_DIR/deploy/hermes-coders"
OPERATOR_SOURCE="$VELVET_APP_DIR/deploy/hermes-operator"
CONTROL_ROOT="${HERMES_OPERATOR_CONTROL_ROOT:-/srv/hermes-operator-control}"
OPERATOR_ENV="$CONTROL_ROOT/operator.env"
CODER_ROUTER_ENV="$CONTROL_ROOT/coders.env"
AGENT_CONTROL_NETWORK="${HERMES_AGENT_CONTROL_NETWORK:-hermes-agent-control}"

for path in \
  "$VELVET_ENV_FILE" \
  "$VELVET_COMPOSE_FILE" \
  "$CODERS_SOURCE/compose.yaml" \
  "$CODERS_SOURCE/SOUL.velvet.md" \
  "$CODERS_SOURCE/SOUL.max.md" \
  "$CODERS_SOURCE/ensure_runtime_config.py" \
  "$CODERS_SOURCE/preflight.py" \
  "$OPERATOR_SOURCE/compose.yaml" \
  "$OPERATOR_SOURCE/coder_router.py" \
  "$OPERATOR_SOURCE/coderctl.py" \
  "$OPERATOR_SOURCE/SOUL.operator.md" \
  "$OPERATOR_ENV" \
  "$CODERS_ROOT/secrets/velvet.env" \
  "$CODERS_ROOT/secrets/max.env"; do
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
  "$CODER_ROUTER_ENV" <<'PY'
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.is_file():
        return result
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def update_env(path: Path) -> dict[str, str]:
    values = parse_env(path)
    key = values.get("API_SERVER_KEY", "")
    if len(key) < 24:
        values["API_SERVER_KEY"] = secrets.token_urlsafe(48)
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            ordered.append(raw)
            continue
        name = line.split("=", 1)[0].strip()
        if name == "API_SERVER_KEY":
            ordered.append(f"API_SERVER_KEY={values['API_SERVER_KEY']}")
        else:
            ordered.append(raw)
        seen.add(name)
    if "API_SERVER_KEY" not in seen:
        if ordered and ordered[-1].strip():
            ordered.append("")
        ordered.append("# Internal Hermes Runs API")
        ordered.append(f"API_SERVER_KEY={values['API_SERVER_KEY']}")
    path.write_text("\n".join(ordered).rstrip() + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return values


velvet_path = Path(sys.argv[1])
max_path = Path(sys.argv[2])
operator_path = Path(sys.argv[3])
router_path = Path(sys.argv[4])
velvet = update_env(velvet_path)
maximum = update_env(max_path)
if velvet["API_SERVER_KEY"] == maximum["API_SERVER_KEY"]:
    maximum["API_SERVER_KEY"] = secrets.token_urlsafe(48)
    lines = max_path.read_text(encoding="utf-8").splitlines()
    max_path.write_text(
        "\n".join(
            f"API_SERVER_KEY={maximum['API_SERVER_KEY']}"
            if line.strip().startswith("API_SERVER_KEY=")
            else line
            for line in lines
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    os.chmod(max_path, 0o600)
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
print("Coder API and router credentials prepared without printing secret values.")
PY

chown "$SERVICE_USER:$SERVICE_USER" \
  "$CODERS_ROOT/secrets/velvet.env" \
  "$CODERS_ROOT/secrets/max.env" \
  "$CODER_ROUTER_ENV"
chmod 0600 \
  "$CODERS_ROOT/secrets/velvet.env" \
  "$CODERS_ROOT/secrets/max.env" \
  "$CODER_ROUTER_ENV"

python3 \
  "$CODERS_SOURCE/ensure_runtime_config.py" \
  "$CODERS_ROOT/data/velvet/config.yaml" \
  "$CODERS_ROOT/data/max/config.yaml"
env HERMES_CODERS_ROOT="$CODERS_ROOT" \
  python3 "$CODERS_SOURCE/preflight.py"

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

python3 - \
  "$hermes_data/SOUL.md" \
  "$OPERATOR_SOURCE/SOUL.operator.md" <<'PY'
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

for project in velvet max; do
  data_dir="$CODERS_ROOT/data/$project"
  source_soul="$CODERS_SOURCE/SOUL.$project.md"
  if [[ ! -d "$data_dir" ]]; then
    echo "Отсутствует coder data directory: $data_dir" >&2
    exit 4
  fi
  install -m 0640 -o "$(stat -c '%u' "$data_dir")" -g "$(stat -c '%g' "$data_dir")" \
    "$source_soul" "$data_dir/SOUL.md"
done

cd "$CODERS_SOURCE"
runuser -u "$SERVICE_USER" -- env \
  HERMES_CODERS_ROOT="$CODERS_ROOT" \
  HERMES_AGENT_CONTROL_NETWORK="$AGENT_CONTROL_NETWORK" \
  docker compose --profile velvet --profile max -f compose.yaml config --quiet
runuser -u "$SERVICE_USER" -- env \
  HERMES_CODERS_ROOT="$CODERS_ROOT" \
  HERMES_AGENT_CONTROL_NETWORK="$AGENT_CONTROL_NETWORK" \
  docker compose --profile velvet --profile max -f compose.yaml up -d --build --force-recreate

cd "$OPERATOR_SOURCE"
runuser -u "$SERVICE_USER" -- env \
  HERMES_CODER_ROUTER_ENV_FILE="$CODER_ROUTER_ENV" \
  HERMES_AGENT_CONTROL_NETWORK="$AGENT_CONTROL_NETWORK" \
  docker compose -f compose.yaml config --quiet
systemctl restart hermes-operator-control.service

if [[ -f "$VELVET_APP_DIR/.env.hermes" ]]; then
  runuser -u "$SERVICE_USER" -- bash -ceu "
    cd '$VELVET_APP_DIR'
    docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
      --profile agent restart hermes
  "
fi

router_healthy=false
for _ in $(seq 1 30); do
  if runuser -u "$SERVICE_USER" -- env \
    HERMES_CODER_ROUTER_ENV_FILE="$CODER_ROUTER_ENV" \
    HERMES_AGENT_CONTROL_NETWORK="$AGENT_CONTROL_NETWORK" \
    docker compose -f "$OPERATOR_SOURCE/compose.yaml" exec -T hermes-coder-router \
      python -c "import json,urllib.request; payload=json.load(urllib.request.urlopen('http://127.0.0.1:8878/health', timeout=3)); raise SystemExit(0 if payload.get('status') == 'ok' else 1)" \
      >/dev/null 2>&1; then
    router_healthy=true
    break
  fi
  sleep 2
done
if [[ "$router_healthy" != "true" ]]; then
  runuser -u "$SERVICE_USER" -- env \
    HERMES_CODER_ROUTER_ENV_FILE="$CODER_ROUTER_ENV" \
    HERMES_AGENT_CONTROL_NETWORK="$AGENT_CONTROL_NETWORK" \
    docker compose -f "$OPERATOR_SOURCE/compose.yaml" logs --tail=100 hermes-coder-router >&2 || true
  echo "Hermes coder router не достиг healthy status." >&2
  exit 5
fi

runuser -u "$SERVICE_USER" -- env \
  HERMES_CODER_ROUTER_ENV_FILE="$CODER_ROUTER_ENV" \
  HERMES_AGENT_CONTROL_NETWORK="$AGENT_CONTROL_NETWORK" \
  docker compose -f "$OPERATOR_SOURCE/compose.yaml" ps
runuser -u "$SERVICE_USER" -- env \
  HERMES_CODERS_ROOT="$CODERS_ROOT" \
  HERMES_AGENT_CONTROL_NETWORK="$AGENT_CONTROL_NETWORK" \
  docker compose --profile velvet --profile max -f "$CODERS_SOURCE/compose.yaml" ps

echo
printf '%s\n' \
  "Hermes coder orchestration installed." \
  "Main Hermes can submit/status/wait/list tasks through /opt/data/tools/coderctl.py." \
  "Coder API keys remain only in coder secrets and the isolated router env."
