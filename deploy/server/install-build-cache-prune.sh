#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run this installer with sudo." >&2
  exit 1
fi

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
SERVICE_SOURCE="$APP_DIR/deploy/systemd/velvet-build-cache-prune.service"
TIMER_SOURCE="$APP_DIR/deploy/systemd/velvet-build-cache-prune.timer"
SERVICE_TARGET="/etc/systemd/system/velvet-build-cache-prune.service"
TIMER_TARGET="/etc/systemd/system/velvet-build-cache-prune.timer"
PRUNE_SCRIPT="$APP_DIR/deploy/server/prune-build-cache.sh"
DOCKER_CONFIG_DIR="$APP_DIR/data/runtime/docker-config"

for path in "$SERVICE_SOURCE" "$TIMER_SOURCE" "$PRUNE_SCRIPT"; do
  if [[ ! -f "$path" ]]; then
    echo "Missing required file: $path" >&2
    exit 2
  fi
done
if ! id velvet >/dev/null 2>&1; then
  echo "Missing service user: velvet" >&2
  exit 2
fi
if [[ ! -x /usr/bin/docker ]]; then
  echo "Docker CLI is unavailable at /usr/bin/docker" >&2
  exit 2
fi

install -d -m 0700 -o velvet -g velvet "$DOCKER_CONFIG_DIR"
install -m 0644 "$SERVICE_SOURCE" "$SERVICE_TARGET"
install -m 0644 "$TIMER_SOURCE" "$TIMER_TARGET"
systemctl daemon-reload
systemctl enable --now velvet-build-cache-prune.timer
systemctl --no-pager --full status velvet-build-cache-prune.timer
systemctl list-timers --all velvet-build-cache-prune.timer --no-pager
