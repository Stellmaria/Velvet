#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите через sudo." >&2
  exit 1
fi

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-$APP_DIR/.env.server}"
COMPOSE_FILE="${VELVET_COMPOSE_FILE:-$APP_DIR/docker-compose.server.yml}"
AUTO_KINDS="${STORAGE_LIBRARIAN_AUTO_ALLOWED_KINDS:-diagnostics,codex,rework,inbox,exports,releases}"
AUTO_BATCH_SIZE="${STORAGE_LIBRARIAN_AUTO_BATCH_SIZE:-1}"
SCAN_INTERVAL="${STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS:-60}"

for path in "$ENV_FILE" "$COMPOSE_FILE"; do
  if [[ ! -f "$path" ]]; then
    echo "Отсутствует обязательный файл: $path" >&2
    exit 2
  fi
done

python3 - "$ENV_FILE" "$AUTO_KINDS" "$AUTO_BATCH_SIZE" "$SCAN_INTERVAL" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
auto_kinds = sys.argv[2].strip()
batch_size = int(sys.argv[3])
scan_interval = int(sys.argv[4])

if not 1 <= batch_size <= 10:
    raise SystemExit("STORAGE_LIBRARIAN_AUTO_BATCH_SIZE должен быть от 1 до 10")
if not 60 <= scan_interval <= 86400:
    raise SystemExit("STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS должен быть от 60 до 86400")
if not auto_kinds:
    raise SystemExit("STORAGE_LIBRARIAN_AUTO_ALLOWED_KINDS не может быть пустым")

lines = path.read_text(encoding="utf-8-sig").splitlines()
values: dict[str, str] = {}
for raw in lines:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

ollama = values.get(
    "STORAGE_LIBRARIAN_OLLAMA_BASE_URL",
    "http://ollama-librarian:11434",
).rstrip("/")
if ollama != "http://ollama-librarian:11434":
    raise SystemExit(
        "Full archive backfill разрешён только через локальный "
        "http://ollama-librarian:11434"
    )

updates = {
    "STORAGE_LIBRARIAN_ENABLED": "true",
    "STORAGE_LIBRARIAN_AUTO_ENQUEUE": "true",
    "STORAGE_LIBRARIAN_AUTO_BACKFILL": "true",
    "STORAGE_LIBRARIAN_AUTO_MIN_OBJECT_ID": "0",
    "STORAGE_LIBRARIAN_AUTO_ALLOWED_KINDS": auto_kinds,
    "STORAGE_LIBRARIAN_AUTO_BATCH_SIZE": str(batch_size),
    "STORAGE_LIBRARIAN_SCAN_INTERVAL_SECONDS": str(scan_interval),
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

printf '%s\n' \
  "Storage Librarian full-archive backfill enabled." \
  "Inference route: local Ollama only." \
  "Automatic enqueue: true." \
  "Archive backfill: true." \
  "Categories: $AUTO_KINDS." \
  "Batch per cycle: $AUTO_BATCH_SIZE." \
  "Scan interval: $SCAN_INTERVAL seconds." \
  "Encrypted, unsupported and oversized objects remain excluded by Librarian policy." \
  "Disable with: sudo bash deploy/hermes-librarian/disable_afk.sh"
