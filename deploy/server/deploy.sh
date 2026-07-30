#!/usr/bin/env bash
set -Eeuo pipefail

umask 077
exec 9>"${TMPDIR:-/tmp}/velvet-deploy.lock"
if ! flock -n 9; then
  echo "Another Velvet deployment is already running." >&2
  exit 75
fi

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-.env.server}"
COMPOSE_FILE="${VELVET_COMPOSE_FILE:-docker-compose.server.yml}"
REMOTE="${VELVET_DEPLOY_REMOTE:-origin}"
BRANCH="${VELVET_DEPLOY_BRANCH:-main}"
HEALTH_ATTEMPTS="${VELVET_HEALTH_ATTEMPTS:-60}"
HEALTH_INTERVAL="${VELVET_HEALTH_INTERVAL:-5}"
START_HERMES="${VELVET_START_HERMES:-0}"

cd "$APP_DIR"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $APP_DIR/$ENV_FILE" >&2
  exit 2
fi
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Missing $APP_DIR/$COMPOSE_FILE" >&2
  exit 2
fi

python3 scripts/server_preflight.py \
  --env-file "$ENV_FILE" \
  --hermes-env .env.hermes \
  --skip-host-tools

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

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Tracked working tree changes detected; deployment aborted." >&2
  git status --short >&2
  exit 3
fi

mkdir -p "$data_dir/backups" "$data_dir/logs" "$data_dir/runtime"
previous_sha="$(git rev-parse HEAD)"
backup_path="$data_dir/backups/predeploy-$(date -u +%Y%m%dT%H%M%SZ)-${previous_sha:0:12}.dump"
deployment_started=0

rollback_code() {
  local exit_code="$?"
  if [[ "$deployment_started" == "1" ]]; then
    echo "Deployment failed; rolling application code back to $previous_sha" >&2
    git reset --hard "$previous_sha" >&2 || true
    "${compose[@]}" build bot >&2 || true
    "${compose[@]}" up -d postgres bot >&2 || true
    echo "Database was not automatically restored." >&2
    echo "Verified pre-deploy dump: $backup_path" >&2
  fi
  exit "$exit_code"
}
trap rollback_code ERR INT TERM

echo "Fetching $REMOTE/$BRANCH..."
git fetch --prune "$REMOTE" "$BRANCH"
target_sha="$(git rev-parse "$REMOTE/$BRANCH")"

if [[ "$target_sha" == "$previous_sha" ]]; then
  echo "Velvet is already at $target_sha"
  exit 0
fi

echo "Creating pre-deploy PostgreSQL dump..."
"${compose[@]}" up -d postgres
"${compose[@]}" exec -T postgres sh -ceu '
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc
' > "$backup_path"
test -s "$backup_path"
chmod 600 "$backup_path"

VELVET_APP_DIR="$APP_DIR" \
VELVET_ENV_FILE="$ENV_FILE" \
VELVET_COMPOSE_FILE="$COMPOSE_FILE" \
  bash deploy/server/verify-dump.sh "$backup_path"

echo "Deploying $target_sha..."
deployment_started=1
git reset --hard "$target_sha"
"${compose[@]}" pull postgres
"${compose[@]}" build --pull bot
"${compose[@]}" up -d --remove-orphans postgres bot

if [[ "$START_HERMES" == "1" ]]; then
  if [[ ! -f .env.hermes ]]; then
    echo "VELVET_START_HERMES=1 but .env.hermes is missing." >&2
    false
  fi
  "${compose[@]}" --profile agent pull hermes
  "${compose[@]}" --profile agent up -d hermes
fi

container_id="$("${compose[@]}" ps -q bot)"
if [[ -z "$container_id" ]]; then
  echo "Velvet bot container was not created." >&2
  false
fi

for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt++)); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
  case "$health" in
    healthy|running)
      "${compose[@]}" exec -T bot python scripts/server_smoke.py --skip-telegram
      deployed_sha="$(git rev-parse HEAD)"
      if [[ "$deployed_sha" != "$target_sha" ]]; then
        echo "Deployed SHA mismatch: expected $target_sha, got $deployed_sha" >&2
        false
      fi
      deployment_started=0
      trap - ERR INT TERM
      echo "Velvet deployment succeeded: $deployed_sha"
      echo "Verified pre-deploy backup: $backup_path"
      "${compose[@]}" ps
      exit 0
      ;;
    unhealthy|exited|dead)
      echo "Velvet health check failed with state: $health" >&2
      "${compose[@]}" logs --tail 200 bot >&2 || true
      false
      ;;
  esac
  sleep "$HEALTH_INTERVAL"
done

echo "Velvet did not become healthy in time." >&2
"${compose[@]}" logs --tail 200 bot >&2 || true
false
