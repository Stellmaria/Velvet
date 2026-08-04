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
TARGET_OVERRIDE="${VELVET_DEPLOY_TARGET_SHA:-}"
IMAGE_OVERRIDE="${VELVET_DEPLOY_IMAGE:-}"
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
if [[ -n "$IMAGE_OVERRIDE" && ! "$IMAGE_OVERRIDE" =~ ^ghcr\.io/stellmaria/velvet@sha256:[0-9a-f]{64}$ ]]; then
  echo "VELVET_DEPLOY_IMAGE must be an immutable Velvet GHCR digest" >&2
  exit 2
fi

python3 scripts/server_preflight.py \
  --env-file "$ENV_FILE" \
  --hermes-env .env.hermes \
  --skip-host-tools

readarray -t deployment_settings < <(python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import sys
from scripts.server_preflight import parse_env_file


def enabled(value: str) -> bool:
    return value.strip().casefold() in {"1", "true", "yes", "on", "да"}


env = parse_env_file(Path(sys.argv[1]))
data_dir = env.get("VELVET_DATA_DIR", "").strip()
if not data_dir:
    raise SystemExit("VELVET_DATA_DIR is missing")
watermark_enabled = enabled(env.get("KRITA_WATERMARK_ENABLED", "false"))
remote_enabled = enabled(env.get("KRITA_REMOTE_WORKER_ENABLED", "false"))
bridge_dir = env.get("KRITA_BRIDGE_DIR", "/app/runtime/krita").strip()
if watermark_enabled and not remote_enabled:
    if bridge_dir != "/app/runtime/krita" and not bridge_dir.startswith("/app/runtime/krita/"):
        raise SystemExit("Server Krita requires KRITA_BRIDGE_DIR inside /app/runtime/krita")
    server_krita = "1"
else:
    server_krita = "0"
print(data_dir)
print(server_krita)
PY
)

data_dir="${deployment_settings[0]}"
krita_server_enabled="${deployment_settings[1]}"
docker_config="${DOCKER_CONFIG:-$data_dir/runtime/docker-config}"
export DOCKER_CONFIG="$docker_config"
export COMPOSE_BAKE="${COMPOSE_BAKE:-false}"
if [[ -n "$IMAGE_OVERRIDE" ]]; then
  export VELVET_IMAGE="$IMAGE_OVERRIDE"
fi
compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Tracked working tree changes detected; deployment aborted." >&2
  git status --short >&2
  exit 3
fi

mkdir -p \
  "$data_dir/backups" \
  "$data_dir/logs" \
  "$data_dir/runtime" \
  "$data_dir/runtime/supervisor" \
  "$docker_config"
chmod 0755 "$data_dir/runtime/supervisor"
chmod 0700 "$docker_config"
if [[ "$krita_server_enabled" == "1" ]]; then
  mkdir -p "$data_dir/runtime/krita"/{sources,requests,responses,outputs,previews,assets}
fi
previous_sha="$(git rev-parse HEAD)"
previous_bot_container="$("${compose[@]}" ps -q bot 2>/dev/null || true)"
previous_bot_image=""
previous_bot_image_id=""
rollback_bot_image=""
if [[ -n "$previous_bot_container" ]]; then
  previous_bot_image="$(docker inspect --format '{{.Config.Image}}' "$previous_bot_container" 2>/dev/null || true)"
  previous_bot_image_id="$(docker inspect --format '{{.Image}}' "$previous_bot_container" 2>/dev/null || true)"
  if [[ "$previous_bot_image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    rollback_bot_image="velvet-bot:rollback-${previous_sha:0:12}"
    docker image tag "$previous_bot_image_id" "$rollback_bot_image"
  fi
fi
backup_path="$data_dir/backups/predeploy-$(date -u +%Y%m%dT%H%M%SZ)-${previous_sha:0:12}.dump"
deployment_started=0

wait_for_service_health() {
  local service="$1"
  VELVET_APP_DIR="$APP_DIR" \
  VELVET_ENV_FILE="$ENV_FILE" \
  VELVET_COMPOSE_FILE="$COMPOSE_FILE" \
    bash deploy/server/wait-compose-health.sh \
      "$service" "$HEALTH_ATTEMPTS" "$HEALTH_INTERVAL"
}

start_core_services() {
  "${compose[@]}" up -d --remove-orphans postgres supervisor-proxy || return
  wait_for_service_health postgres || return
  wait_for_service_health supervisor-proxy
}

start_bot_service() {
  "${compose[@]}" rm -sf bot >/dev/null 2>&1 || true
  "${compose[@]}" up -d --no-deps bot
}

rollback_code() {
  local exit_code="$?"
  local rollback_failed=0
  trap - ERR INT TERM
  set +e
  if [[ "$deployment_started" == "1" ]]; then
    echo "Deployment failed; rolling application code back to $previous_sha" >&2
    if ! git reset --hard "$previous_sha" >&2; then
      rollback_failed=1
    fi
    if ! "${compose[@]}" build supervisor-proxy >&2; then
      rollback_failed=1
    fi
    if [[ -n "$rollback_bot_image" ]] && docker image inspect "$rollback_bot_image" >/dev/null 2>&1; then
      export VELVET_IMAGE="$rollback_bot_image"
    elif [[ "$previous_bot_image" =~ ^ghcr\.io/stellmaria/velvet@sha256:[0-9a-f]{64}$ ]]; then
      if docker pull "$previous_bot_image" >&2; then
        export VELVET_IMAGE="$previous_bot_image"
      else
        rollback_failed=1
      fi
    else
      unset VELVET_IMAGE
      if ! "${compose[@]}" build bot >&2; then
        rollback_failed=1
      fi
    fi
    if (( rollback_failed == 0 )) && ! start_core_services >&2; then
      rollback_failed=1
    fi
    if (( rollback_failed == 0 )) && ! start_bot_service >&2; then
      rollback_failed=1
    fi
    if (( rollback_failed == 0 )) && ! wait_for_service_health bot >&2; then
      rollback_failed=1
    fi
    if (( rollback_failed == 0 )) && ! "${compose[@]}" exec -T bot python scripts/server_smoke.py --skip-telegram >&2; then
      rollback_failed=1
    fi
    if [[ "$krita_server_enabled" == "1" ]]; then
      if ! "${compose[@]}" --profile watermark build krita >&2; then
        rollback_failed=1
      elif ! "${compose[@]}" --profile watermark up -d --no-deps krita >&2; then
        rollback_failed=1
      elif ! wait_for_service_health krita >&2; then
        rollback_failed=1
      fi
    fi
    if (( rollback_failed == 0 )); then
      echo "Rollback restored the previous bot image and passed health checks." >&2
    else
      echo "Rollback did not restore a verified healthy runtime; manual intervention is required." >&2
    fi
    echo "Database was not automatically restored." >&2
    echo "Verified pre-deploy dump: $backup_path" >&2
  fi
  exit "$exit_code"
}
trap rollback_code ERR INT TERM

echo "Fetching $REMOTE/$BRANCH..."
git fetch --prune "$REMOTE" "$BRANCH"
remote_sha="$(git rev-parse "$REMOTE/$BRANCH")"
if [[ -n "$TARGET_OVERRIDE" ]]; then
  target_sha="$(git rev-parse --verify "${TARGET_OVERRIDE}^{commit}")"
  if ! git merge-base --is-ancestor "$target_sha" "$remote_sha"; then
    echo "Requested deployment target is not an ancestor of $REMOTE/$BRANCH: $target_sha" >&2
    exit 4
  fi
  echo "Using verified deployment target $target_sha"
else
  target_sha="$remote_sha"
fi

if [[ "$target_sha" == "$previous_sha" && -z "$IMAGE_OVERRIDE" ]]; then
  echo "Velvet is already at $target_sha"
  exit 0
fi

echo "Creating pre-deploy PostgreSQL dump..."
"${compose[@]}" up -d postgres
# POSTGRES_USER and POSTGRES_DB must expand inside the container shell.
# shellcheck disable=SC2016
"${compose[@]}" exec -T postgres sh -ceu '
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc
' > "$backup_path"
test -s "$backup_path"
# The bot container mounts this protected directory and uploads verified dumps
# to Telegram storage. Keep the parent directory private, but make the dump
# readable when the host deploy user and the fixed container UID differ.
chmod 0644 "$backup_path"

VELVET_APP_DIR="$APP_DIR" \
VELVET_ENV_FILE="$ENV_FILE" \
VELVET_COMPOSE_FILE="$COMPOSE_FILE" \
  bash deploy/server/verify-dump.sh "$backup_path"

echo "Deploying $target_sha..."
deployment_started=1
git reset --hard "$target_sha"
"${compose[@]}" pull postgres
"${compose[@]}" build --pull supervisor-proxy

if [[ -n "$IMAGE_OVERRIDE" ]]; then
  echo "Pulling verified application image $IMAGE_OVERRIDE..."
  docker pull "$IMAGE_OVERRIDE"
  image_revision="$(docker image inspect "$IMAGE_OVERRIDE" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
  if [[ "${image_revision,,}" != "${target_sha,,}" ]]; then
    echo "Image revision mismatch: expected $target_sha, got ${image_revision:-<missing>}" >&2
    false
  fi
  pulled_id="$(docker image inspect "$IMAGE_OVERRIDE" --format '{{.Id}}')"
  if [[ ! "$pulled_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "Unable to resolve immutable application image ID" >&2
    false
  fi
else
  echo "No verified image digest supplied; building local rollback image."
  "${compose[@]}" build --pull bot
fi

if [[ "$krita_server_enabled" == "1" ]]; then
  "${compose[@]}" --profile watermark build --pull krita
fi

start_core_services
start_bot_service

if [[ "$krita_server_enabled" == "1" ]]; then
  "${compose[@]}" --profile watermark rm -sf krita >/dev/null 2>&1 || true
  "${compose[@]}" --profile watermark up -d --no-deps krita
else
  "${compose[@]}" --profile watermark stop --timeout 45 krita >/dev/null 2>&1 || true
fi

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
      if [[ "$krita_server_enabled" == "1" ]]; then
        VELVET_APP_DIR="$APP_DIR" \
        VELVET_ENV_FILE="$ENV_FILE" \
        VELVET_COMPOSE_FILE="$COMPOSE_FILE" \
          bash deploy/server/wait-compose-health.sh krita "$HEALTH_ATTEMPTS" "$HEALTH_INTERVAL"
        VELVET_APP_DIR="$APP_DIR" \
        VELVET_ENV_FILE="$ENV_FILE" \
          bash deploy/server/krita-smoke.sh "$ENV_FILE"
      fi
      deployed_sha="$(git rev-parse HEAD)"
      if [[ "$deployed_sha" != "$target_sha" ]]; then
        echo "Deployed SHA mismatch: expected $target_sha, got $deployed_sha" >&2
        false
      fi
      if [[ -n "$IMAGE_OVERRIDE" ]]; then
        running_image_id="$(docker inspect --format '{{.Image}}' "$container_id")"
        expected_image_id="$(docker image inspect "$IMAGE_OVERRIDE" --format '{{.Id}}')"
        if [[ "$running_image_id" != "$expected_image_id" ]]; then
          echo "Running image mismatch: expected $expected_image_id, got $running_image_id" >&2
          false
        fi
      fi
      deployment_started=0
      trap - ERR INT TERM
      if [[ -n "$rollback_bot_image" ]]; then
        docker image rm "$rollback_bot_image" >/dev/null 2>&1 || true
      fi
      echo "Velvet deployment succeeded: $deployed_sha"
      if [[ -n "$IMAGE_OVERRIDE" ]]; then
        echo "Verified application image: $IMAGE_OVERRIDE"
      fi
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
