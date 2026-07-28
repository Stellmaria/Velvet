#!/usr/bin/env bash
set -Eeuo pipefail

umask 077
exec 9>"${TMPDIR:-/tmp}/velvet-deploy.lock"
if ! flock -n 9; then
  echo "Another Velvet deployment is already running." >&2
  exit 75
fi

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
REMOTE="${VELVET_DEPLOY_REMOTE:-origin}"
BRANCH="${VELVET_DEPLOY_BRANCH:-main}"
HEALTH_ATTEMPTS="${VELVET_HEALTH_ATTEMPTS:-60}"
HEALTH_INTERVAL="${VELVET_HEALTH_INTERVAL:-5}"

cd "$APP_DIR"

if [[ ! -f .env ]]; then
  echo "Missing $APP_DIR/.env" >&2
  exit 2
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

: "${POSTGRES_USER:?POSTGRES_USER must be set in .env}"
: "${POSTGRES_DB:?POSTGRES_DB must be set in .env}"

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Tracked working tree changes detected; deployment aborted." >&2
  git status --short >&2
  exit 3
fi

mkdir -p backups logs runtime
previous_sha="$(git rev-parse HEAD)"
backup_path="backups/predeploy-$(date -u +%Y%m%dT%H%M%SZ)-${previous_sha:0:12}.dump"
deployment_started=0

rollback_code() {
  local exit_code="$?"
  if [[ "$deployment_started" == "1" ]]; then
    echo "Deployment failed; rolling application code back to $previous_sha" >&2
    git reset --hard "$previous_sha" >&2 || true
    docker compose build bot >&2 || true
    docker compose up -d postgres bot >&2 || true
    echo "Database was not automatically restored. Verified pre-deploy dump: $backup_path" >&2
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
docker compose up -d postgres
docker compose exec -T postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$backup_path"
test -s "$backup_path"
chmod 600 "$backup_path"

echo "Deploying $target_sha..."
deployment_started=1
git reset --hard "$target_sha"
docker compose pull postgres
if [[ -f .env.hermes ]]; then
  docker compose --profile agent pull hermes
fi
docker compose build --pull bot
docker compose up -d --remove-orphans postgres bot
if [[ -f .env.hermes ]]; then
  docker compose --profile agent up -d hermes
fi

container_id="$(docker compose ps -q bot)"
if [[ -z "$container_id" ]]; then
  echo "Velvet bot container was not created." >&2
  false
fi

for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt++)); do
  health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id")"
  case "$health" in
    healthy|running)
      deployed_sha="$(git rev-parse HEAD)"
      if [[ "$deployed_sha" != "$target_sha" ]]; then
        echo "Deployed SHA mismatch: expected $target_sha, got $deployed_sha" >&2
        false
      fi
      deployment_started=0
      trap - ERR INT TERM
      echo "Velvet deployment succeeded: $deployed_sha"
      echo "Pre-deploy backup: $backup_path"
      docker compose ps
      exit 0
      ;;
    unhealthy|exited|dead)
      echo "Velvet health check failed with state: $health" >&2
      docker compose logs --tail 200 bot >&2 || true
      false
      ;;
  esac
  sleep "$HEALTH_INTERVAL"
done

echo "Velvet did not become healthy in time." >&2
docker compose logs --tail 200 bot >&2 || true
false
