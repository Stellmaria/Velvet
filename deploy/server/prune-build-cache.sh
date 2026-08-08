#!/usr/bin/env bash
set -Eeuo pipefail

DOCKER_BIN="${DOCKER_BIN:-/usr/bin/docker}"
LOCK_PATH="${VELVET_DEPLOY_LOCK:-${TMPDIR:-/tmp}/velvet-deploy.lock}"
PRUNE_AGE="${VELVET_BUILD_CACHE_PRUNE_AGE:-168h}"

if [[ ! "$PRUNE_AGE" =~ ^[1-9][0-9]*h$ ]]; then
  echo "VELVET_BUILD_CACHE_PRUNE_AGE must be a positive hour duration, got: $PRUNE_AGE" >&2
  exit 2
fi
if [[ ! -x "$DOCKER_BIN" ]]; then
  echo "Docker CLI is unavailable: $DOCKER_BIN" >&2
  exit 2
fi
if [[ -e "$LOCK_PATH" && ! -f "$LOCK_PATH" ]]; then
  echo "Refusing unexpected Velvet deploy lock path: $LOCK_PATH" >&2
  exit 3
fi

exec 9>"$LOCK_PATH"
if ! flock -n 9; then
  echo "Skipping BuildKit cache prune because a Velvet deploy is active."
  exit 0
fi

"$DOCKER_BIN" builder prune -af --filter "until=$PRUNE_AGE"
