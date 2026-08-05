#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите launcher installer через sudo." >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCE_DIR="${HERMES_SANDBOX_SOURCE_DIR:-$SCRIPT_DIR}"
REPO_ROOT="${HERMES_RELEASE_ROOT:-$(cd "$SOURCE_DIR/../.." && pwd -P)}"
CODERS_SOURCE="${HERMES_CODERS_SOURCE_DIR:-$REPO_ROOT/deploy/hermes-coders}"
INSTALL_ROOT="${HERMES_SANDBOX_INSTALL_ROOT:-/usr/local/lib/hermes-sandbox-launcher}"
RELEASES_DIR="$INSTALL_ROOT/releases"
CURRENT_LINK="$INSTALL_ROOT/current"
ROOT="${HERMES_CODERS_ROOT:-/srv/hermes-coders}"
APP_GROUP="${HERMES_CODERS_APP_GROUP:-velvet}"
SANDBOX_GROUP="${HERMES_SANDBOX_GROUP:-hermes-sandbox}"
NETWORK="${HERMES_SANDBOX_NETWORK:-hermes-sandbox-egress}"
HERMES_UID_VALUE="${HERMES_UID:-10000}"
HERMES_GID_VALUE="${HERMES_GID:-10000}"
SOCKET_SOURCE="$REPO_ROOT/deploy/systemd/hermes-sandbox-launcher.socket"
SERVICE_SOURCE="$REPO_ROOT/deploy/systemd/hermes-sandbox-launcher.service"
SOCKET_TARGET="/etc/systemd/system/hermes-sandbox-launcher.socket"
SERVICE_TARGET="/etc/systemd/system/hermes-sandbox-launcher.service"
RUNNER_PROFILE_SOURCE="$CODERS_SOURCE/security/apparmor-hermes-codex-runner"
RUN_PROFILE_SOURCE="$CODERS_SOURCE/security/apparmor-hermes-codex-run"
RUNNER_PROFILE_TARGET="/etc/apparmor.d/hermes-codex-runner"
RUN_PROFILE_TARGET="/etc/apparmor.d/hermes-codex-run"

if [[ ! "$NETWORK" =~ ^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$ ]]; then
  echo "Небезопасное имя HERMES_SANDBOX_NETWORK: $NETWORK" >&2
  exit 2
fi
for value in "$REPO_ROOT" "$SOURCE_DIR" "$CODERS_SOURCE" "$INSTALL_ROOT"; do
  if [[ "$value" != /* ]]; then
    echo "Launcher paths должны быть абсолютными: $value" >&2
    exit 2
  fi
done

for required in \
  "$SOURCE_DIR/launcher.py" \
  "$SOURCE_DIR/launcher_contract.py" \
  "$SOURCE_DIR/launcher_runtime.py" \
  "$CODERS_SOURCE/sandbox_entrypoint.py" \
  "$SOCKET_SOURCE" \
  "$SERVICE_SOURCE" \
  "$RUNNER_PROFILE_SOURCE" \
  "$RUN_PROFILE_SOURCE"; do
  if [[ ! -f "$required" || -L "$required" ]]; then
    echo "Отсутствует или небезопасен launcher artifact: $required" >&2
    exit 2
  fi
done

EXACT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
if [[ ! "$EXACT_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Launcher release не привязан к exact Git SHA." >&2
  exit 2
fi
RELEASE_DIR="$RELEASES_DIR/$EXACT_SHA"

if [[ "$(cat /sys/module/apparmor/parameters/enabled 2>/dev/null)" != "Y" ]]; then
  echo "AppArmor не включён; launcher installation остановлена" >&2
  exit 3
fi
docker info >/dev/null

if ! getent group "$SANDBOX_GROUP" >/dev/null; then
  groupadd --system "$SANDBOX_GROUP"
fi
SANDBOX_GID_VALUE="$(getent group "$SANDBOX_GROUP" | cut -d: -f3)"
if [[ ! "$SANDBOX_GID_VALUE" =~ ^[0-9]+$ ]]; then
  echo "Не удалось определить GID группы $SANDBOX_GROUP" >&2
  exit 3
fi

install -d -o root -g root -m 0755 "$INSTALL_ROOT" "$RELEASES_DIR"
if [[ -e "$RELEASE_DIR" || -L "$RELEASE_DIR" ]]; then
  if [[ -L "$RELEASE_DIR" || ! -d "$RELEASE_DIR" ]]; then
    echo "Existing launcher release path unsafe: $RELEASE_DIR" >&2
    exit 3
  fi
else
  stage_dir="$(mktemp -d "$RELEASES_DIR/.stage-$EXACT_SHA.XXXXXX")"
  cleanup_stage() { rm -rf -- "${stage_dir:-}"; }
  trap cleanup_stage EXIT
  install -o root -g root -m 0555 "$SOURCE_DIR/launcher.py" "$stage_dir/launcher.py"
  install -o root -g root -m 0444 \
    "$SOURCE_DIR/launcher_contract.py" "$stage_dir/launcher_contract.py"
  install -o root -g root -m 0444 \
    "$SOURCE_DIR/launcher_runtime.py" "$stage_dir/launcher_runtime.py"
  install -o root -g root -m 0555 \
    "$CODERS_SOURCE/sandbox_entrypoint.py" "$stage_dir/sandbox_entrypoint.py"
  mv -T "$stage_dir" "$RELEASE_DIR"
  trap - EXIT
fi
chown -R root:root "$RELEASE_DIR"
find "$RELEASE_DIR" -type d -exec chmod 0555 {} +
find "$RELEASE_DIR" -type f -name '*.py' -exec chmod a-w {} +

install -d -o "$HERMES_UID_VALUE" -g "$HERMES_GID_VALUE" -m 0750 \
  "$ROOT/codex-runs" \
  "$ROOT/codex-runs/velvet" \
  "$ROOT/codex-runs/max" \
  "$ROOT/codex-runs/velvet/workspaces" \
  "$ROOT/codex-runs/max/workspaces" \
  "$ROOT/codex-runs/velvet/probes" \
  "$ROOT/codex-runs/max/probes"
install -d -o root -g "$APP_GROUP" -m 0750 "$ROOT"
install -d -o root -g root -m 0700 /run/hermes-sandbox-private
install -d -o root -g "$SANDBOX_GROUP" -m 0750 /run/hermes-sandbox

existing_velvet=""
existing_max=""
if [[ -f "$ROOT/launcher.env" && ! -L "$ROOT/launcher.env" ]]; then
  existing_velvet="$(sed -n 's/^HERMES_SANDBOX_VELVET_IMAGE=//p' "$ROOT/launcher.env")"
  existing_max="$(sed -n 's/^HERMES_SANDBOX_MAX_IMAGE=//p' "$ROOT/launcher.env")"
fi

launcher_env_tmp="$(mktemp "$ROOT/.launcher.env.XXXXXX")"
trap 'rm -f -- "$launcher_env_tmp"' EXIT
cat > "$launcher_env_tmp" <<EOF
HERMES_CODERS_ROOT=$ROOT
HERMES_SANDBOX_GID=$SANDBOX_GID_VALUE
HERMES_SANDBOX_NETWORK=$NETWORK
HERMES_SANDBOX_INSTALL_DIR=$CURRENT_LINK
HERMES_SANDBOX_PENDING_INSTALL_DIR=$RELEASE_DIR
HERMES_SANDBOX_VELVET_IMAGE=$existing_velvet
HERMES_SANDBOX_MAX_IMAGE=$existing_max
HERMES_UID=$HERMES_UID_VALUE
HERMES_GID=$HERMES_GID_VALUE
EOF
chown root:"$APP_GROUP" "$launcher_env_tmp"
chmod 0640 "$launcher_env_tmp"
mv -f "$launcher_env_tmp" "$ROOT/launcher.env"
trap - EXIT

if ! docker network inspect "$NETWORK" >/dev/null 2>&1; then
  docker network create --driver bridge --attachable "$NETWORK" >/dev/null
fi

install -o root -g root -m 0644 "$RUNNER_PROFILE_SOURCE" "$RUNNER_PROFILE_TARGET"
install -o root -g root -m 0644 "$RUN_PROFILE_SOURCE" "$RUN_PROFILE_TARGET"
apparmor_parser -r "$RUNNER_PROFILE_TARGET"
apparmor_parser -r "$RUN_PROFILE_TARGET"
install -o root -g root -m 0644 "$SOCKET_SOURCE" "$SOCKET_TARGET"
install -o root -g root -m 0644 "$SERVICE_SOURCE" "$SERVICE_TARGET"
systemctl daemon-reload

printf '%s\n' \
  "Hermes sandbox launcher staged from exact release: $EXACT_SHA" \
  "- pending release: $RELEASE_DIR" \
  "- current symlink unchanged: $CURRENT_LINK" \
  "- socket/service installed but traffic not activated" \
  "- immutable image pinning is still required"
