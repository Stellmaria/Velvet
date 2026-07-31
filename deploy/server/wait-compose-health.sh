#!/usr/bin/env bash
set -Eeuo pipefail

service="${1:?compose service is required}"
attempts="${2:-60}"
interval="${3:-5}"
APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-.env.server}"
COMPOSE_FILE="${VELVET_COMPOSE_FILE:-docker-compose.server.yml}"

cd "$APP_DIR"
compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")
if [[ "$service" == "krita" ]]; then
  compose+=(--profile watermark)
fi

container_id="$("${compose[@]}" ps -q "$service")"
if [[ -z "$container_id" ]]; then
  echo "Compose service was not created: $service" >&2
  exit 1
fi

for ((attempt = 1; attempt <= attempts; attempt++)); do
  state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
  case "$state" in
    healthy|running)
      echo "$service is $state"
      exit 0
      ;;
    unhealthy|exited|dead)
      echo "$service health failed with state: $state" >&2
      "${compose[@]}" logs --tail 200 "$service" >&2 || true
      exit 1
      ;;
  esac
  sleep "$interval"
done

echo "$service did not become healthy in time" >&2
"${compose[@]}" logs --tail 200 "$service" >&2 || true
exit 1
