#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите installer через sudo." >&2
  exit 1
fi

VELVET_APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
VELVET_ENV_FILE="${VELVET_ENV_FILE:-$VELVET_APP_DIR/.env.server}"
HERMES_ENV_FILE="${HERMES_ENV_FILE:-$VELVET_APP_DIR/.env.hermes}"
VELVET_COMPOSE_FILE="${VELVET_COMPOSE_FILE:-$VELVET_APP_DIR/docker-compose.server.yml}"
SERVICE_USER="${HERMES_ORCHESTRATION_SERVICE_USER:-velvet}"
SOURCE_DIR="$VELVET_APP_DIR/deploy/hermes-librarian"
UNIT_SOURCE="$VELVET_APP_DIR/deploy/systemd/velvet-librarian.service"
UNIT_TARGET="/etc/systemd/system/velvet-librarian.service"

for path in \
  "$VELVET_ENV_FILE" \
  "$HERMES_ENV_FILE" \
  "$VELVET_COMPOSE_FILE" \
  "$SOURCE_DIR/compose.yaml" \
  "$SOURCE_DIR/prepare_profile.py" \
  "$SOURCE_DIR/SOUL.md" \
  "$SOURCE_DIR/AGENTS.md" \
  "$UNIT_SOURCE"
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

python3 - "$VELVET_ENV_FILE" <<'PY'
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8-sig").splitlines()
values = {}
for raw in lines:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

key = values.get("STORAGE_LIBRARIAN_HERMES_API_KEY", "")
if len(key) < 24:
    key = secrets.token_urlsafe(48)

updates = {
    "STORAGE_LIBRARIAN_HERMES_BASE_URL": "http://librarian-hermes:8642",
    "STORAGE_LIBRARIAN_HERMES_API_KEY": key,
}
result = []
seen = set()
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
print("Velvet Librarian credentials prepared without printing secret values.")
PY

readarray -t resolved < <(python3 - "$VELVET_ENV_FILE" <<'PY'
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
print(values.get("HERMES_IMAGE", "nousresearch/hermes-agent@sha256:f7b35053268f532f98955195c909f15a230470fbcbdacaa9fdecb95707dad04a"))
PY
)
VELVET_DATA_DIR="${resolved[0]}"
HERMES_IMAGE="${resolved[1]}"
SOURCE_CONFIG="$VELVET_DATA_DIR/hermes/config.yaml"
TARGET_DIR="$VELVET_DATA_DIR/hermes-librarian"

if [[ ! -f "$SOURCE_CONFIG" ]]; then
  echo "Отсутствует config основного Hermes: $SOURCE_CONFIG" >&2
  exit 3
fi

source_uid="$(stat -c '%u' "$VELVET_DATA_DIR/hermes")"
source_gid="$(stat -c '%g' "$VELVET_DATA_DIR/hermes")"
install -d -m 0750 -o "$source_uid" -g "$source_gid" "$TARGET_DIR"

# Use the pinned Hermes image so profile YAML is parsed by the same runtime
# dependency set that will later load it. No network is available during prep.
docker run --rm \
  --network none \
  --entrypoint python \
  -v "$SOURCE_CONFIG:/source/config.yaml:ro" \
  -v "$SOURCE_DIR:/bootstrap:ro" \
  -v "$TARGET_DIR:/target" \
  "$HERMES_IMAGE" \
  /bootstrap/prepare_profile.py \
  /source/config.yaml \
  /target \
  /bootstrap/SOUL.md \
  /bootstrap/AGENTS.md

chown -R "$source_uid:$source_gid" "$TARGET_DIR"
find "$TARGET_DIR" -type d -exec chmod 0750 {} +
find "$TARGET_DIR" -type f -exec chmod 0640 {} +

# Validate the exact deny-all profile with the same image and parser.
docker run --rm \
  --network none \
  --entrypoint python \
  -v "$TARGET_DIR/config.yaml:/profile/config.yaml:ro" \
  "$HERMES_IMAGE" \
  - <<'PY'
from pathlib import Path
import yaml

config = yaml.safe_load(Path("/profile/config.yaml").read_text(encoding="utf-8")) or {}
platform = config.get("platform_toolsets") or {}
agent = config.get("agent") or {}
disabled = set(agent.get("disabled_toolsets") or [])
required = {"terminal", "file", "web", "browser", "messaging", "memory", "delegation", "code_execution", "skills"}
assert platform.get("api_server") == [], platform
assert required.issubset(disabled), sorted(required - disabled)
assert config.get("mcp_servers") == {}, config.get("mcp_servers")
print("Velvet Librarian deny-all tool contract: OK")
PY

install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
systemctl daemon-reload
systemctl enable --now velvet-librarian.service

runuser -u "$SERVICE_USER" -- bash -ceu "
  cd '$VELVET_APP_DIR'
  docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
    up -d --force-recreate bot
"

healthy=false
for _ in $(seq 1 45); do
  if runuser -u "$SERVICE_USER" -- bash -ceu "
    cd '$VELVET_APP_DIR'
    docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
      exec -T bot python - <<'PY'
import json
import os
import urllib.request

request = urllib.request.Request(
    os.environ['STORAGE_LIBRARIAN_HERMES_BASE_URL'].rstrip('/') + '/health',
    headers={'Authorization': 'Bearer ' + os.environ['STORAGE_LIBRARIAN_HERMES_API_KEY']},
)
with urllib.request.urlopen(request, timeout=3) as response:
    payload = json.load(response)
raise SystemExit(0 if payload.get('status') == 'ok' else 1)
PY
  " >/dev/null 2>&1; then
    healthy=true
    break
  fi
  sleep 2
done

if [[ "$healthy" != "true" ]]; then
  systemctl --no-pager --full status velvet-librarian.service >&2 || true
  runuser -u "$SERVICE_USER" -- \
    docker compose --env-file "$VELVET_ENV_FILE" -f "$SOURCE_DIR/compose.yaml" \
      logs --tail=100 librarian-hermes >&2 || true
  echo "Velvet Librarian API не достиг healthy status." >&2
  exit 4
fi

printf '%s\n' \
  "Velvet Librarian profile installed." \
  "Dedicated API key configured." \
  "Bot-to-Librarian health verified." \
  "Automatic enqueue remains controlled by STORAGE_LIBRARIAN_AUTO_ENQUEUE."
