#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите через sudo." >&2
  exit 1
fi

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-$APP_DIR/.env.server}"
COMPOSE_FILE="${VELVET_COMPOSE_FILE:-$APP_DIR/docker-compose.server.yml}"
AUTO_KINDS="${STORAGE_LIBRARIAN_AUTO_ALLOWED_KINDS:-diagnostics,releases}"
AUTO_BATCH_SIZE="${STORAGE_LIBRARIAN_AUTO_BATCH_SIZE:-1}"
SCAN_INTERVAL="${STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS:-300}"

for path in "$ENV_FILE" "$COMPOSE_FILE"; do
  if [[ ! -f "$path" ]]; then
    echo "Отсутствует обязательный файл: $path" >&2
    exit 2
  fi
done

cd "$APP_DIR"

max_object_id="$(
  docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
    exec -T bot python - <<'PY'
import asyncio
import os

import asyncpg


async def main() -> None:
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if not database_url:
        raise SystemExit("DATABASE_URL отсутствует внутри bot container")
    connection = await asyncpg.connect(database_url)
    try:
        value = await connection.fetchval(
            "SELECT COALESCE(MAX(id), 0) FROM telegram_storage_objects"
        )
    finally:
        await connection.close()
    print(int(value or 0))


asyncio.run(main())
PY
)"

if [[ ! "$max_object_id" =~ ^[0-9]+$ ]] || [[ "$max_object_id" -le 0 ]]; then
  echo "Не удалось определить безопасный Storage cutoff: $max_object_id" >&2
  exit 3
fi

python3 - "$ENV_FILE" "$max_object_id" "$AUTO_KINDS" "$AUTO_BATCH_SIZE" "$SCAN_INTERVAL" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
cutoff = int(sys.argv[2])
auto_kinds = sys.argv[3].strip()
batch_size = int(sys.argv[4])
scan_interval = int(sys.argv[5])

if not 1 <= batch_size <= 10:
    raise SystemExit("STORAGE_LIBRARIAN_AUTO_BATCH_SIZE должен быть от 1 до 10")
if not 60 <= scan_interval <= 86400:
    raise SystemExit("STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS должен быть от 60 до 86400")
if not auto_kinds:
    raise SystemExit("STORAGE_LIBRARIAN_AUTO_ALLOWED_KINDS не может быть пустым")

updates = {
    "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "true",
    "STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID": str(cutoff),
    "STORAGE_LIBRARIAN_AUTO_ALLOWED_KINDS": auto_kinds,
    "STORAGE_LIBRARIAN_AUTO_BATCH_SIZE": str(batch_size),
    "STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS": str(scan_interval),
}
lines = path.read_text(encoding="utf-8-sig").splitlines()
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

docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" \
  up -d --force-recreate bot

printf '%s\n' \
  "Storage Librarian AFK new-only enabled." \
  "Cutoff Storage ID: $max_object_id." \
  "AFK categories: $AUTO_KINDS." \
  "Batch per cycle: $AUTO_BATCH_SIZE." \
  "Scan interval: $SCAN_INTERVAL seconds." \
  "Objects at or below the cutoff will not be auto-enqueued."
