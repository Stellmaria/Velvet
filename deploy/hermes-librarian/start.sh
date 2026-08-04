#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-$APP_DIR/.env.server}"
COMPOSE_FILE="${LIBRARIAN_COMPOSE_FILE:-$APP_DIR/deploy/hermes-librarian/compose.yaml}"
readarray -t model_aliases < <(python3 - "$ENV_FILE" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

values: dict[str, str] = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

print(os.getenv("STORAGE_LIBRARIAN_TEXT_MODEL") or values.get(
    "STORAGE_LIBRARIAN_TEXT_MODEL", "velvet-librarian-text:v1"
))
print(os.getenv("STORAGE_LIBRARIAN_VISION_MODEL") or values.get(
    "STORAGE_LIBRARIAN_VISION_MODEL", "velvet-librarian-vision:v1"
))
PY
)
TEXT_MODEL="${model_aliases[0]}"
VISION_MODEL="${model_aliases[1]}"
TEXT_SOURCE_MODEL="qwen3:4b-instruct"
VISION_SOURCE_MODEL="qwen3.5:9b-q4_K_M"

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

"${compose[@]}" up -d ollama-librarian

ready=false
for _ in $(seq 1 90); do
  if "${compose[@]}" exec -T ollama-librarian ollama list >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 2
done

if [[ "$ready" != "true" ]]; then
  "${compose[@]}" logs --tail=120 ollama-librarian >&2 || true
  echo "Локальный Ollama Librarian не достиг healthy state." >&2
  exit 1
fi

if ! "${compose[@]}" exec -T ollama-librarian \
  ollama show "$TEXT_SOURCE_MODEL" >/dev/null 2>&1; then
  "${compose[@]}" exec -T ollama-librarian ollama pull "$TEXT_SOURCE_MODEL"
fi
if ! "${compose[@]}" exec -T ollama-librarian \
  ollama show "$VISION_SOURCE_MODEL" >/dev/null 2>&1; then
  "${compose[@]}" exec -T ollama-librarian ollama pull "$VISION_SOURCE_MODEL"
fi

# Recreate aliases so Modelfile changes are applied without deleting the
# persistent volume. Source pulls are skipped when the model is already local.
"${compose[@]}" exec -T ollama-librarian \
  ollama create "$TEXT_MODEL" -f /bootstrap/Modelfile.text
"${compose[@]}" exec -T ollama-librarian \
  ollama create "$VISION_MODEL" -f /bootstrap/Modelfile.vision
"${compose[@]}" exec -T ollama-librarian ollama show "$TEXT_MODEL" >/dev/null
"${compose[@]}" exec -T ollama-librarian ollama show "$VISION_MODEL" >/dev/null

"${compose[@]}" up -d --force-recreate librarian-hermes
