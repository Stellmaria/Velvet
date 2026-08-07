#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите через sudo." >&2
  exit 1
fi

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-$APP_DIR/.env.server}"
COMPOSE_FILE="${VELVET_COMPOSE_FILE:-$APP_DIR/docker-compose.server.yml}"

for path in "$ENV_FILE" "$COMPOSE_FILE"; do
  if [[ ! -f "$path" ]]; then
    echo "Отсутствует обязательный файл: $path" >&2
    exit 2
  fi
done

python3 - "$ENV_FILE" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8-sig").splitlines()
updates = {
    "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "false",
    "STORAGE_LIBRARIAN_AUTO_BACKFILL": "false",
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
PY

cd "$APP_DIR"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
  up -d --force-recreate bot

echo "Storage Librarian AFK/backfill disabled. Manual commands remain available."
