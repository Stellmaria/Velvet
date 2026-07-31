#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-.env.server}"
UNIT_SOURCE="$APP_DIR/deploy/systemd/velvet-krita.service"
UNIT_TARGET="/etc/systemd/system/velvet-krita.service"

cd "$APP_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $APP_DIR/$ENV_FILE" >&2
  exit 2
fi
if [[ ! -f "$UNIT_SOURCE" ]]; then
  echo "Missing $UNIT_SOURCE" >&2
  exit 2
fi

python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
updates = {
    "KRITA_WATERMARK_ENABLED": "true",
    "KRITA_REMOTE_WORKER_ENABLED": "false",
    "KRITA_BRIDGE_DIR": "/app/runtime/krita",
}
lines = path.read_text(encoding="utf-8").splitlines()
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
if seen != updates.keys():
    result.append("")
    result.append("# Headless Krita watermark worker on this VPS")
    for key, value in updates.items():
        if key not in seen:
            result.append(f"{key}={value}")
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

install -d -m 0750 -o 10001 -g 10001 \
  "$data_dir/runtime/krita" \
  "$data_dir/runtime/krita/sources" \
  "$data_dir/runtime/krita/requests" \
  "$data_dir/runtime/krita/responses" \
  "$data_dir/runtime/krita/outputs" \
  "$data_dir/runtime/krita/previews" \
  "$data_dir/runtime/krita/assets"
install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
systemctl daemon-reload

# The bot must reread KRITA_WATERMARK_ENABLED before the worker accepts jobs.
systemctl reload-or-restart velvet-compose.service
VELVET_APP_DIR="$APP_DIR" VELVET_ENV_FILE="$ENV_FILE" \
  bash deploy/server/wait-compose-health.sh bot 90 5

systemctl enable --now velvet-krita.service
systemctl --no-pager --full status velvet-krita.service
