#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

bridge_dir="${KRITA_BRIDGE_DIR:-/app/runtime/krita}"
screen="${KRITA_XVFB_SCREEN:-1920x1080x24}"

case "$bridge_dir" in
  /app/runtime/krita|/app/runtime/krita/*) ;;
  *)
    echo "KRITA_BRIDGE_DIR must stay inside /app/runtime/krita: $bridge_dir" >&2
    exit 2
    ;;
esac

mkdir -p \
  "$bridge_dir/requests" \
  "$bridge_dir/responses" \
  "$bridge_dir/outputs" \
  "$bridge_dir/sources" \
  "$bridge_dir/previews" \
  "$bridge_dir/assets"
rm -f "$bridge_dir/krita-heartbeat.json"

exec dbus-run-session -- \
  xvfb-run -a \
    -e /proc/self/fd/2 \
    -s "-screen 0 $screen -nolisten tcp -noreset" \
    /usr/bin/krita --nosplash
