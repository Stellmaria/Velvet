#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-$APP_DIR/.env.server}"
COMPOSE_FILE="${VELVET_COMPOSE_FILE:-$APP_DIR/docker-compose.server.yml}"

for path in "$ENV_FILE" "$COMPOSE_FILE"; do
  if [[ ! -f "$path" ]]; then
    echo "Отсутствует обязательный файл: $path" >&2
    exit 2
  fi
done

cd "$APP_DIR"
compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

bot_container="$("${compose[@]}" ps -q bot 2>/dev/null || true)"
if [[ -z "$bot_container" ]]; then
  echo "Bot container отсутствует; Arthur lifecycle не может выбирать image из .env.server." >&2
  echo "Сначала выполните verified application deploy." >&2
  exit 3
fi

bot_running="$(docker inspect --format '{{.State.Running}}' "$bot_container" 2>/dev/null || true)"
if [[ "$bot_running" != "true" ]]; then
  echo "Bot container не запущен; отказ от lifecycle recreate без доказанного running image." >&2
  exit 3
fi

current_image_id="$(docker inspect --format '{{.Image}}' "$bot_container" 2>/dev/null || true)"
if [[ ! "$current_image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "Не удалось доказать точный image ID работающего bot: ${current_image_id:-<missing>}" >&2
  exit 4
fi

short_id="${current_image_id#sha256:}"
preserved_image_ref="velvet-bot:arthur-preserve-${short_id:0:16}"
cleanup() {
  docker image rm "$preserved_image_ref" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker image tag "$current_image_id" "$preserved_image_ref"

# Shell environment overrides the stale VELVET_IMAGE value from .env.server for
# Compose interpolation. This lifecycle operation is configuration-only: it must
# recreate bot from the exact image that was already running, never deploy code.
VELVET_IMAGE="$preserved_image_ref" \
  "${compose[@]}" up -d --no-deps --force-recreate bot

new_container="$("${compose[@]}" ps -q bot 2>/dev/null || true)"
if [[ -z "$new_container" ]]; then
  echo "Bot container не создан после lifecycle recreate." >&2
  exit 5
fi

new_image_id="$(docker inspect --format '{{.Image}}' "$new_container" 2>/dev/null || true)"
if [[ "$new_image_id" != "$current_image_id" ]]; then
  echo "Arthur lifecycle image mismatch: expected $current_image_id, got ${new_image_id:-<missing>}" >&2
  exit 6
fi

new_running="$(docker inspect --format '{{.State.Running}}' "$new_container" 2>/dev/null || true)"
if [[ "$new_running" != "true" ]]; then
  echo "Bot container не запущен после lifecycle recreate." >&2
  exit 7
fi

printf 'Arthur lifecycle preserved bot image: %s\n' "$current_image_id"
