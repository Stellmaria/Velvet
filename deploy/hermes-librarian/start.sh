#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-$APP_DIR/.env.server}"
COMPOSE_FILE="${LIBRARIAN_COMPOSE_FILE:-$APP_DIR/deploy/hermes-librarian/compose.yaml}"
LOCAL_MODEL="${STORAGE_LIBRARIAN_LOCAL_MODEL:-velvet-librarian-local:v1}"
SOURCE_MODEL="qwen3.5:9b-q4_K_M"

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

if ! "${compose[@]}" exec -T ollama-librarian ollama show "$SOURCE_MODEL" >/dev/null 2>&1; then
  "${compose[@]}" exec -T ollama-librarian ollama pull "$SOURCE_MODEL"
fi

# Recreate the local alias every time so Modelfile changes are applied even
# when the persistent Ollama volume already contains an older alias.
"${compose[@]}" exec -T ollama-librarian \
  ollama create "$LOCAL_MODEL" -f /bootstrap/Modelfile
"${compose[@]}" exec -T ollama-librarian ollama show "$LOCAL_MODEL" >/dev/null

"${compose[@]}" up -d --force-recreate librarian-hermes
