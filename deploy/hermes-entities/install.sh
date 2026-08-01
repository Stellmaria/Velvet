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
UNIT_SOURCE="$VELVET_APP_DIR/deploy/systemd/hermes-entities-reconcile.service"
UNIT_TARGET="/etc/systemd/system/hermes-entities-reconcile.service"

for path in \
  "$VELVET_ENV_FILE" \
  "$VELVET_COMPOSE_FILE" \
  "$HERMES_ENV_FILE" \
  "$VELVET_APP_DIR/deploy/hermes-entities/reconcile.sh" \
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

python3 - "$HERMES_ENV_FILE" <<'PY'
from pathlib import Path
import os
import sys

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8-sig").splitlines()
key = "API_SERVER_MODEL_NAME"
value = "kael"
result = []
found = False
for raw in lines:
    if raw.strip().startswith(key + "="):
        if not found:
            result.append(f"{key}={value}")
            found = True
        continue
    result.append(raw)
if not found:
    if result and result[-1].strip():
        result.append("")
    result.extend(("# Kael server identity", f"{key}={value}"))
path.write_text("\n".join(result).rstrip() + "\n", encoding="utf-8")
os.chmod(path, 0o600)
PY

chmod 0750 "$VELVET_APP_DIR/deploy/hermes-entities/reconcile.sh"
"$VELVET_APP_DIR/deploy/hermes-entities/reconcile.sh"

install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
systemctl daemon-reload
systemctl enable hermes-entities-reconcile.service
systemctl restart hermes-entities-reconcile.service

runuser -u "$SERVICE_USER" -- bash -ceu "
  cd '$VELVET_APP_DIR'
  docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
    --profile agent up -d hermes
  docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
    --profile agent restart hermes
"

if systemctl list-unit-files hermes-coders.service --no-legend 2>/dev/null | grep -q '^hermes-coders.service'; then
  systemctl restart hermes-coders.service
fi
if systemctl list-unit-files hermes-coder-router.service --no-legend 2>/dev/null | grep -q '^hermes-coder-router.service'; then
  systemctl restart hermes-coder-router.service
fi

for _ in $(seq 1 45); do
  if runuser -u "$SERVICE_USER" -- \
    docker compose --env-file "$VELVET_ENV_FILE" -f "$VELVET_COMPOSE_FILE" \
      --profile agent exec -T hermes \
      python /opt/data/tools/coderctl.py health all >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

runuser -u "$SERVICE_USER" -- \
  docker compose --env-file "$VELVET_ENV_FILE" -f "$VELVET_COMPOSE_FILE" \
    --profile agent exec -T hermes \
    python /opt/data/tools/coderctl.py health all >/dev/null

python3 - "$HERMES_ENV_FILE" <<'PY'
from pathlib import Path
import json
import sys
import urllib.parse
import urllib.request

values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

token = values.get("TELEGRAM_BOT_TOKEN", "")
if not token:
    raise SystemExit("TELEGRAM_BOT_TOKEN основного Hermes отсутствует")

name = "Kᴀᴇʟ Vᴇʟᴠᴇᴛ"
data = urllib.parse.urlencode({"name": name}).encode("utf-8")
request = urllib.request.Request(
    f"https://api.telegram.org/bot{token}/setMyName",
    data=data,
    method="POST",
)
with urllib.request.urlopen(request, timeout=20) as response:
    payload = json.load(response)
if payload.get("ok") is not True or payload.get("result") is not True:
    raise SystemExit("Telegram setMyName не подтвердил переименование")

request = urllib.request.Request(
    f"https://api.telegram.org/bot{token}/getMyName",
    method="POST",
)
with urllib.request.urlopen(request, timeout=20) as response:
    payload = json.load(response)
actual = ((payload.get("result") or {}).get("name") or "").strip()
if actual != name:
    raise SystemExit(f"Telegram вернул неожиданное имя: {actual!r}")
print(f"Telegram display name: {actual}")
PY

runuser -u "$SERVICE_USER" -- \
  docker compose --env-file "$VELVET_ENV_FILE" -f "$VELVET_COMPOSE_FILE" \
    --profile agent exec -T hermes \
    /command/s6-setuidgid hermes \
    sh -ceu '
      test "$(id -u)" = "10000"
      test -r /opt/data/SOUL.md
      test -r /opt/data/AGENTS.md
      test -x /opt/data/tools/opsctl.py
      test -x /opt/data/tools/coderctl.py
      test -x /opt/data/tools/runctl.py
      test -w /opt/data/orchestration/tasks.json
      test -w /opt/data/orchestration/tasks.json.lock
    '

printf '%s\n' \
  "Kael identity installed." \
  "Coder entities and project contexts installed." \
  "Kael tools and orchestration ledger permissions verified."
