#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Canonical Hermes release requires root." >&2
  exit 1
fi

TARGET_SHA="${1:-}"
APP_DIR="${2:-/srv/velvet}"
ROOT="${HERMES_CODERS_ROOT:-/srv/hermes-coders}"
REPO_ROOT="${HERMES_RELEASE_ROOT:-}"
SOURCE_DIR="$REPO_ROOT/deploy/hermes-coders"
RELEASE_ROOT="$ROOT/releases"
CURRENT_LINK="$RELEASE_ROOT/current-hermes-coders"
ROLLBACK_ROOT="$ROOT/rollbacks"
OVERRIDE_FILE="$ROOT/compose.bwrap.override.yaml"
VELVET_CONTAINER=hermes-coders-hermes-coder-velvet-1
MAX_CONTAINER=hermes-coders-hermes-coder-max-1

if [[ ! "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Target SHA must be an exact lowercase 40-character commit." >&2
  exit 2
fi
if [[ -z "$REPO_ROOT" || "$REPO_ROOT" != /* ]]; then
  echo "HERMES_RELEASE_ROOT must name the exact detached release worktree." >&2
  exit 2
fi
for required in \
  "$REPO_ROOT/.git" \
  "$SOURCE_DIR/install.sh" \
  "$SOURCE_DIR/compose.yaml" \
  "$SOURCE_DIR/compose.runtime.yaml" \
  "$SOURCE_DIR/compose.security.yaml" \
  "$REPO_ROOT/deploy/hermes-sandbox-launcher/install.sh" \
  "$REPO_ROOT/deploy/systemd/hermes-coders.service"; do
  if [[ ! -e "$required" ]]; then
    echo "Exact release artifact is missing: $required" >&2
    exit 2
  fi
done
if [[ "$(git -C "$REPO_ROOT" rev-parse HEAD)" != "$TARGET_SHA" ]]; then
  echo "Release worktree HEAD does not match target SHA." >&2
  exit 2
fi

exec 9>"${TMPDIR:-/tmp}/velvet-hermes-coder-release.lock"
if ! flock -n 9; then
  echo "Another Hermes coder release is already running." >&2
  exit 75
fi

cd "$APP_DIR"
test -d .git
git fetch --no-tags --prune origin main
REMOTE_MAIN="$(git rev-parse origin/main)"
if [[ "$REMOTE_MAIN" != "$TARGET_SHA" ]]; then
  echo "Target is no longer current main: $TARGET_SHA != $REMOTE_MAIN" >&2
  exit 2
fi

install -d -o root -g root -m 0750 "$ROLLBACK_ROOT"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_DIR="$ROLLBACK_ROOT/issue-594-$STAMP-$TARGET_SHA"
install -d -o root -g root -m 0700 "$BACKUP_DIR/rootfs"
EXISTING_MANIFEST="$BACKUP_DIR/existing-paths.txt"
: > "$EXISTING_MANIFEST"

ARTIFACT_PATHS=(
  /usr/local/lib/hermes-sandbox-launcher
  /etc/systemd/system/hermes-sandbox-launcher.socket
  /etc/systemd/system/hermes-sandbox-launcher.service
  /etc/systemd/system/hermes-coders.service
  /etc/apparmor.d/hermes-codex-runner
  /etc/apparmor.d/hermes-codex-run
  /srv/hermes-coders/launcher.env
)
backup_path() {
  local path="$1"
  if [[ -e "$path" || -L "$path" ]]; then
    printf '%s\n' "$path" >> "$EXISTING_MANIFEST"
    install -d -m 0700 "$BACKUP_DIR/rootfs$(dirname "$path")"
    cp -a -- "$path" "$BACKUP_DIR/rootfs$path"
  fi
}
for path in "${ARTIFACT_PATHS[@]}"; do
  backup_path "$path"
done

PREVIOUS_LINK=""
if [[ -L "$CURRENT_LINK" ]]; then
  PREVIOUS_LINK="$(readlink -f "$CURRENT_LINK")"
fi
PREVIOUS_COMPOSE_DIR=""
if [[ -n "$PREVIOUS_LINK" && -d "$PREVIOUS_LINK/deploy/hermes-coders" ]]; then
  PREVIOUS_COMPOSE_DIR="$PREVIOUS_LINK/deploy/hermes-coders"
elif docker inspect "$VELVET_CONTAINER" >/dev/null 2>&1; then
  previous_source="$(docker inspect "$VELVET_CONTAINER" --format '{{range .Mounts}}{{if eq .Destination "/app/codex_tier_runner.py"}}{{.Source}}{{end}}{{end}}')"
  if [[ -n "$previous_source" ]]; then
    PREVIOUS_COMPOSE_DIR="$(dirname "$previous_source")"
  fi
fi
printf '%s\n' "$PREVIOUS_LINK" > "$BACKUP_DIR/previous-link.txt"
printf '%s\n' "$PREVIOUS_COMPOSE_DIR" > "$BACKUP_DIR/previous-compose-dir.txt"

PREVIOUS_VELVET_IMAGE=""
PREVIOUS_MAX_IMAGE=""
if docker inspect "$VELVET_CONTAINER" >/dev/null 2>&1; then
  PREVIOUS_VELVET_IMAGE="$(docker inspect "$VELVET_CONTAINER" --format '{{.Image}}')"
fi
if docker inspect "$MAX_CONTAINER" >/dev/null 2>&1; then
  PREVIOUS_MAX_IMAGE="$(docker inspect "$MAX_CONTAINER" --format '{{.Image}}')"
fi
printf '%s\n' "$PREVIOUS_VELVET_IMAGE" > "$BACKUP_DIR/velvet-image.txt"
printf '%s\n' "$PREVIOUS_MAX_IMAGE" > "$BACKUP_DIR/max-image.txt"

restore_artifacts() {
  local path
  for path in "${ARTIFACT_PATHS[@]}"; do
    rm -rf -- "$path"
    if grep -Fxq "$path" "$EXISTING_MANIFEST"; then
      install -d -m 0755 "$(dirname "$path")"
      cp -a -- "$BACKUP_DIR/rootfs$path" "$path"
    fi
  done
}

rollback() {
  local exit_code="$?"
  trap - ERR INT TERM
  echo "Hermes canonical release failed; restoring previous runtime." >&2
  restore_artifacts || true
  if [[ -n "$PREVIOUS_LINK" ]]; then
    link_tmp="$RELEASE_ROOT/.current-hermes-coders.rollback.$$"
    ln -s "$PREVIOUS_LINK" "$link_tmp"
    mv -Tf "$link_tmp" "$CURRENT_LINK"
  else
    rm -f -- "$CURRENT_LINK"
  fi
  if [[ -n "$PREVIOUS_VELVET_IMAGE" ]]; then
    docker tag "$PREVIOUS_VELVET_IMAGE" velvet-codex-coder-velvet:local || true
  fi
  if [[ -n "$PREVIOUS_MAX_IMAGE" ]]; then
    docker tag "$PREVIOUS_MAX_IMAGE" velvet-codex-coder-max:local || true
  fi
  systemctl daemon-reload || true
  systemctl stop hermes-sandbox-launcher.service hermes-sandbox-launcher.socket || true
  if [[ -f /etc/systemd/system/hermes-sandbox-launcher.socket ]]; then
    systemctl enable --now hermes-sandbox-launcher.socket || true
  fi
  if [[ -n "$PREVIOUS_COMPOSE_DIR" && -d "$PREVIOUS_COMPOSE_DIR" ]]; then
    rollback_compose=(
      docker compose
      --project-name hermes-coders
      --profile velvet
      --profile max
      -f compose.yaml
      -f compose.runtime.yaml
      -f compose.security.yaml
    )
    # Compatibility override is permitted only in rollback of the previously
    # running production contract. Canonical activation above never uses it.
    if [[ -f "$OVERRIDE_FILE" ]]; then
      rollback_compose+=( -f "$OVERRIDE_FILE" )
    fi
    (
      cd "$PREVIOUS_COMPOSE_DIR"
      HERMES_CODERS_ROOT="$ROOT" \
      HERMES_AGENT_CONTROL_NETWORK=hermes-agent-control \
        "${rollback_compose[@]}" up -d --no-build --force-recreate
    ) || true
  fi
  exit "$exit_code"
}
trap rollback ERR INT TERM

HERMES_RELEASE_ROOT="$REPO_ROOT" \
HERMES_CODERS_SOURCE_DIR="$SOURCE_DIR" \
HERMES_CODERS_ROOT="$ROOT" \
  "$SOURCE_DIR/install.sh"

test -L "$CURRENT_LINK"
test "$(readlink -f "$CURRENT_LINK")" = "$REPO_ROOT"
test "$(systemctl show hermes-coders.service -p ActiveState --value)" = active
test "$(systemctl show hermes-coders.service -p SubState --value)" = exited
test "$(systemctl show hermes-coders.service -p ExecMainStatus --value)" = 0

expected_runner_sha="$(sha256sum "$SOURCE_DIR/codex_launcher_runner.py" | awk '{print $1}')"
for container in "$VELVET_CONTAINER" "$MAX_CONTAINER"; do
  test "$(docker inspect "$container" --format '{{.State.Status}}')" = running
  test "$(docker inspect "$container" --format '{{.State.Health.Status}}')" = healthy
  test "$(docker inspect "$container" --format '{{.RestartCount}}')" -eq 0
  test "$(docker inspect "$container" --format '{{json .HostConfig.Init}}')" = true
  security="$(docker inspect "$container" --format '{{json .HostConfig.SecurityOpt}}')"
  grep -F 'apparmor=hermes-codex-runner' <<<"$security" >/dev/null
  if grep -Eq 'unconfined|seccomp=unconfined' <<<"$security"; then
    echo "Canonical coder container uses an unconfined security option." >&2
    false
  fi
  actual_runner_sha="$(docker exec "$container" sha256sum /app/codex_launcher_runner.py | awk '{print $1}')"
  test "$actual_runner_sha" = "$expected_runner_sha"
  container_zombies="$(docker exec "$container" python -c 'from pathlib import Path; print(sum(1 for p in Path("/proc").glob("[0-9]*/stat") if ") Z " in p.read_text(errors="ignore")))')"
  test "$container_zombies" -eq 0
done

PYTHONPATH="$SOURCE_DIR" python3 - <<'PY'
from sandbox_launcher_client import SandboxLauncherClient

client = SandboxLauncherClient()
ping = client.ping()
assert ping.get('backend') == 'host-docker-launcher'
assert ping.get('nested_bwrap') is False
for project in ('velvet', 'max'):
    result = client.probe(project)
    assert int(result.get('returncode', 1)) == 0, result.get('stderr')
PY

host_zombies="$(ps -eo stat= | awk '$1 ~ /^Z/ {count++} END {print count+0}')"
test "$host_zombies" -eq 0
trap - ERR INT TERM

printf '%s\n' \
  "Hermes canonical release succeeded: $TARGET_SHA" \
  "Release root: $REPO_ROOT" \
  "Rollback bundle: $BACKUP_DIR" \
  "Compatibility override was not used for canonical activation."
