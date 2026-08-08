#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-.env.server}"
SOURCE_COMMIT="${VELVET_GATEWAY_SOURCE_COMMIT:-}"
IMAGE_DIGEST="${VELVET_GATEWAY_IMAGE:-}"
REMOTE="${VELVET_DEPLOY_REMOTE:-origin}"
BRANCH="${VELVET_DEPLOY_BRANCH:-main}"
HEALTH_ATTEMPTS="${VELVET_GATEWAY_HEALTH_ATTEMPTS:-30}"
HEALTH_INTERVAL="${VELVET_GATEWAY_HEALTH_INTERVAL:-4}"

if [[ ! "$SOURCE_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]]; then
  echo "VELVET_GATEWAY_SOURCE_COMMIT must be an exact 40-character SHA." >&2
  exit 2
fi
if [[ ! "$IMAGE_DIGEST" =~ ^ghcr\.io/stellmaria/velvet-vision-gateway@sha256:[0-9a-f]{64}$ ]]; then
  echo "VELVET_GATEWAY_IMAGE must be an immutable verified vision gateway digest." >&2
  exit 2
fi
if [[ ! -d "$APP_DIR" ]]; then
  echo "Missing application directory: $APP_DIR" >&2
  exit 2
fi

cd "$APP_DIR"
checkout_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$checkout_root" || "$(cd "$checkout_root" && pwd -P)" != "$(pwd -P)" ]]; then
  echo "$APP_DIR is not the root of a Git checkout." >&2
  exit 2
fi
if [[ ! -f "$ENV_FILE" || -L "$ENV_FILE" ]]; then
  echo "Production env file is missing or unsafe: $APP_DIR/$ENV_FILE" >&2
  exit 2
fi

umask 077
exec 9>"${TMPDIR:-/tmp}/velvet-vision-gateway-deploy.lock"
if ! flock -n 9; then
  echo "Another vision gateway deployment is already running." >&2
  exit 75
fi

state_dir="$(mktemp -d "${TMPDIR:-/tmp}/velvet-gateway-deploy.XXXXXX")"
source_dir="$state_dir/source"
env_backup="$state_dir/env.before"
rollback_tag=""
deployment_started=0
old_gateway_image_id=""
old_gateway_image_ref=""

cleanup_source() {
  rm -rf -- "$state_dir"
}

restore_env() {
  if [[ -f "$env_backup" ]]; then
    cp -p -- "$env_backup" "$ENV_FILE"
  fi
}

wait_for_gateway_health() {
  local cid=""
  local state=""
  local attempt
  for ((attempt = 1; attempt <= HEALTH_ATTEMPTS; attempt++)); do
    cid="$("${compose[@]}" ps -q vision-gateway 2>/dev/null || true)"
    if [[ -n "$cid" ]]; then
      state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid")"
      case "$state" in
        healthy|running)
          printf '%s\n' "$cid"
          return 0
          ;;
        unhealthy|exited|dead)
          echo "vision-gateway entered terminal state: $state" >&2
          return 1
          ;;
      esac
    fi
    sleep "$HEALTH_INTERVAL"
  done
  echo "vision-gateway did not become healthy in time." >&2
  return 1
}

rollback() {
  local rc=$?
  trap - ERR INT TERM EXIT
  set +e
  if (( deployment_started )); then
    echo "Vision gateway deployment failed; restoring previous image." >&2
    restore_env
    if [[ -n "$rollback_tag" ]] && docker image inspect "$rollback_tag" >/dev/null 2>&1; then
      export VISION_GATEWAY_IMAGE="$rollback_tag"
      "${compose[@]}" up -d --no-deps --no-build --pull never vision-gateway >&2
      rollback_cid="$(wait_for_gateway_health 2>/dev/null || true)"
      if [[ -n "$rollback_cid" && "$(docker inspect --format '{{.Image}}' "$rollback_cid")" == "$old_gateway_image_id" ]]; then
        echo "Previous vision gateway image restored." >&2
      else
        echo "Rollback did not restore the previous healthy vision gateway." >&2
      fi
    else
      echo "Rollback image tag is unavailable; manual intervention is required." >&2
    fi
  fi
  if [[ -n "$rollback_tag" ]]; then
    docker image rm "$rollback_tag" >/dev/null 2>&1 || true
  fi
  cleanup_source
  exit "$rc"
}
trap rollback ERR INT TERM
trap cleanup_source EXIT

echo "Fetching $REMOTE/$BRANCH for gateway deployment provenance..."
git fetch --no-tags --prune "$REMOTE" "$BRANCH"
git cat-file -e "${SOURCE_COMMIT}^{commit}"
remote_head="$(git rev-parse "$REMOTE/$BRANCH")"
if ! git merge-base --is-ancestor "$SOURCE_COMMIT" "$remote_head"; then
  echo "Requested gateway source is not an ancestor of $REMOTE/$BRANCH." >&2
  exit 4
fi

mkdir -p "$source_dir"
git archive "$SOURCE_COMMIT" | tar -x -C "$source_dir"
test -f "$source_dir/docker-compose.server.yml"

cp -p -- "$ENV_FILE" "$env_backup"

docker pull "$IMAGE_DIGEST"
image_revision="$(docker image inspect "$IMAGE_DIGEST" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
image_component="$(docker image inspect "$IMAGE_DIGEST" --format '{{index .Config.Labels "org.opencontainers.image.component"}}')"
if [[ "${image_revision,,}" != "${SOURCE_COMMIT,,}" ]]; then
  echo "Vision gateway image revision mismatch: expected $SOURCE_COMMIT, got ${image_revision:-<missing>}." >&2
  exit 5
fi
if [[ "$image_component" != "vision-gateway" ]]; then
  echo "Vision gateway component label mismatch: ${image_component:-<missing>}." >&2
  exit 5
fi
new_gateway_image_id="$(docker image inspect "$IMAGE_DIGEST" --format '{{.Id}}')"
if [[ ! "$new_gateway_image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
  echo "Unable to resolve verified vision gateway image ID." >&2
  exit 5
fi

compose=(
  docker compose
  --project-name velvet
  --env-file "$APP_DIR/$ENV_FILE"
  -f "$source_dir/docker-compose.server.yml"
  --profile vision
)

bot_cid_before="$("${compose[@]}" ps -q bot)"
runtime_cid_before="$("${compose[@]}" ps -q vision-runtime)"
gateway_cid_before="$("${compose[@]}" ps -q vision-gateway)"
test -n "$bot_cid_before"
test -n "$runtime_cid_before"
test -n "$gateway_cid_before"
test "$(docker inspect --format '{{.State.Running}}' "$bot_cid_before")" = true
test "$(docker inspect --format '{{.State.Running}}' "$runtime_cid_before")" = true

old_gateway_image_id="$(docker inspect --format '{{.Image}}' "$gateway_cid_before")"
old_gateway_image_ref="$(docker inspect --format '{{.Config.Image}}' "$gateway_cid_before")"
echo "Current vision gateway image: $old_gateway_image_ref"
if [[ "$old_gateway_image_id" == "$new_gateway_image_id" ]]; then
  echo "Vision gateway already runs the requested image: $IMAGE_DIGEST"
  exit 0
fi

rollback_tag="velvet-vision-gateway:rollback-${SOURCE_COMMIT:0:12}-$$"
docker image tag "$old_gateway_image_id" "$rollback_tag"
deployment_started=1

python3 - "$APP_DIR/$ENV_FILE" "$IMAGE_DIGEST" <<'PY'
from __future__ import annotations

import os
import stat
import sys
import tempfile
from pathlib import Path

path = Path(sys.argv[1])
expected = sys.argv[2]
raw_lines = path.read_text(encoding="utf-8-sig").splitlines()
result: list[str] = []
replaced = False
for raw in raw_lines:
    if "=" in raw and raw.split("=", 1)[0].strip() == "VISION_GATEWAY_IMAGE":
        if not replaced:
            result.append(f"VISION_GATEWAY_IMAGE={expected}")
            replaced = True
        continue
    result.append(raw)
if not replaced:
    if result and result[-1].strip():
        result.append("")
    result.append(f"VISION_GATEWAY_IMAGE={expected}")
payload = "\n".join(result).rstrip() + "\n"

mode = stat.S_IMODE(path.stat().st_mode)
fd, temporary = tempfile.mkstemp(prefix=".env.server.gateway.", dir=path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temporary, mode)
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY

export VISION_GATEWAY_IMAGE="$IMAGE_DIGEST"
"${compose[@]}" up -d --no-deps --no-build --pull never vision-gateway
gateway_cid_after="$(wait_for_gateway_health)"

if [[ "$(docker inspect --format '{{.Image}}' "$gateway_cid_after")" != "$new_gateway_image_id" ]]; then
  echo "Running vision gateway image ID does not match verified digest." >&2
  false
fi
if [[ "$(docker inspect --format '{{.Config.Image}}' "$gateway_cid_after")" != "$IMAGE_DIGEST" ]]; then
  echo "Running vision gateway config image is not the immutable digest." >&2
  false
fi

running_revision="$(docker image inspect "$new_gateway_image_id" --format '{{index .Config.Labels "org.opencontainers.image.revision"}}')"
if [[ "${running_revision,,}" != "${SOURCE_COMMIT,,}" ]]; then
  echo "Running vision gateway revision does not match source commit." >&2
  false
fi

bot_cid_after="$("${compose[@]}" ps -q bot)"
runtime_cid_after="$("${compose[@]}" ps -q vision-runtime)"
if [[ "$bot_cid_after" != "$bot_cid_before" ]]; then
  echo "Bot container changed during gateway-only deployment." >&2
  false
fi
if [[ "$runtime_cid_after" != "$runtime_cid_before" ]]; then
  echo "Vision runtime container changed during gateway-only deployment." >&2
  false
fi

deployment_started=0
trap - ERR INT TERM
docker image rm "$rollback_tag" >/dev/null 2>&1 || true
rollback_tag=""
echo "Vision gateway deployment succeeded: source=$SOURCE_COMMIT image=$IMAGE_DIGEST"
echo "Verified unchanged bot container: $bot_cid_after"
echo "Verified unchanged vision runtime container: $runtime_cid_after"
