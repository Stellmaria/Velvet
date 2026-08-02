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
result: list[str] = []
seen = False
for raw in lines:
    if "=" in raw and raw.split("=", 1)[0].strip() == "STORAGE_LIBRARIAN_AUTO_ENQUEUE":
        if not seen:
            result.append("STORAGE_LIBRARIAN_AUTO_ENQUEUE=false")
            seen = True
        continue
    result.append(raw)
if not seen:
    if result and result[-1].strip():
        result.append("")
    result.append("STORAGE_LIBRARIAN_AUTO_ENQUEUE=false")
path.write_text("\n".join(result).rstrip() + "\n", encoding="utf-8")
os.chmod(path, 0o600)
PY

cd "$APP_DIR"
docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
  up -d --force-recreate bot

echo "Storage Librarian AFK disabled. Manual commands remain available."
