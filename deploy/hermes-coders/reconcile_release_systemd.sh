#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите через sudo." >&2
  exit 1
fi

HERMES_ROOT="${HERMES_CODERS_ROOT:-/srv/hermes-coders}"
RELEASE_LINK="$HERMES_ROOT/releases/current-hermes-coders"
CODER_UNIT=hermes-coders.service
ROUTER_UNIT=hermes-coder-router.service
SYSTEMD_DIR=/etc/systemd/system
LEGACY_DROPIN="$SYSTEMD_DIR/$CODER_UNIT.d/20-bwrap-runtime.conf"
LEGACY_OVERRIDE="$HERMES_ROOT/compose.bwrap.override.yaml"

release_dir="$(readlink -f "$RELEASE_LINK")"
case "$release_dir" in
  "$HERMES_ROOT"/releases/[0-9a-f][0-9a-f]*) ;;
  *)
    echo "current-hermes-coders указывает вне approved release root: $release_dir" >&2
    exit 2
    ;;
esac

release_sha="$(git -C "$release_dir" rev-parse HEAD)"
if [[ ! "$release_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "Не удалось определить exact release SHA." >&2
  exit 2
fi
if [[ "$(basename "$release_dir")" != "$release_sha" ]]; then
  echo "Release directory не соответствует exact SHA: $release_dir" >&2
  exit 2
fi

coder_dir="$release_dir/deploy/hermes-coders"
router_dir="$release_dir/deploy/hermes-orchestration"
unit_source_dir="$release_dir/deploy/systemd"

for required in \
  "$coder_dir/compose.yaml" \
  "$coder_dir/compose.runtime.yaml" \
  "$coder_dir/compose.security.yaml" \
  "$coder_dir/runtime_smoke.py" \
  "$coder_dir/tier_provider_smoke.py" \
  "$router_dir/compose.yaml" \
  "$router_dir/router_smoke.py" \
  "$unit_source_dir/$CODER_UNIT" \
  "$unit_source_dir/$ROUTER_UNIT"; do
  if [[ ! -f "$required" ]]; then
    echo "Отсутствует release artifact: $required" >&2
    exit 3
  fi
done

for unit_file in "$unit_source_dir/$CODER_UNIT" "$unit_source_dir/$ROUTER_UNIT"; do
  if grep -Fq '/srv/velvet/deploy/hermes-' "$unit_file"; then
    echo "Unit всё ещё зависит от mutable /srv/velvet: $unit_file" >&2
    exit 3
  fi
  if ! grep -Fq "$RELEASE_LINK" "$unit_file"; then
    echo "Unit не использует approved release link: $unit_file" >&2
    exit 3
  fi
done

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
backup_dir="/var/backups/hermes-coders-systemd/$stamp-$release_sha"
install -d -o root -g root -m 0700 "$backup_dir"

backup_if_present() {
  local source="$1"
  local name="$2"
  if [[ -e "$source" || -L "$source" ]]; then
    cp -a -- "$source" "$backup_dir/$name"
  fi
}

backup_if_present "$SYSTEMD_DIR/$CODER_UNIT" "$CODER_UNIT"
backup_if_present "$SYSTEMD_DIR/$ROUTER_UNIT" "$ROUTER_UNIT"
backup_if_present "$LEGACY_DROPIN" 20-bwrap-runtime.conf
backup_if_present "$LEGACY_OVERRIDE" compose.bwrap.override.yaml

rollback_units() {
  local status="$?"
  trap - ERR INT TERM
  echo "Systemd reconciliation failed; restoring unit files from $backup_dir" >&2

  if [[ -f "$backup_dir/$CODER_UNIT" ]]; then
    install -o root -g root -m 0644 "$backup_dir/$CODER_UNIT" "$SYSTEMD_DIR/$CODER_UNIT"
  else
    rm -f -- "$SYSTEMD_DIR/$CODER_UNIT"
  fi
  if [[ -f "$backup_dir/$ROUTER_UNIT" ]]; then
    install -o root -g root -m 0644 "$backup_dir/$ROUTER_UNIT" "$SYSTEMD_DIR/$ROUTER_UNIT"
  else
    rm -f -- "$SYSTEMD_DIR/$ROUTER_UNIT"
  fi
  if [[ -f "$backup_dir/20-bwrap-runtime.conf" ]]; then
    install -d -o root -g root -m 0755 "$(dirname "$LEGACY_DROPIN")"
    install -o root -g root -m 0644 \
      "$backup_dir/20-bwrap-runtime.conf" "$LEGACY_DROPIN"
  fi

  systemctl daemon-reload || true
  exit "$status"
}
trap rollback_units ERR INT TERM

install -o root -g root -m 0644 \
  "$unit_source_dir/$CODER_UNIT" "$SYSTEMD_DIR/$CODER_UNIT"
install -o root -g root -m 0644 \
  "$unit_source_dir/$ROUTER_UNIT" "$SYSTEMD_DIR/$ROUTER_UNIT"

# The repository-managed security layer replaces this historical production drop-in.
if [[ -e "$LEGACY_DROPIN" || -L "$LEGACY_DROPIN" ]]; then
  rm -f -- "$LEGACY_DROPIN"
fi

systemctl daemon-reload
systemctl enable "$CODER_UNIT" "$ROUTER_UNIT"
systemctl reset-failed "$CODER_UNIT" "$ROUTER_UNIT" || true

if systemctl is-active --quiet "$CODER_UNIT"; then
  systemctl reload "$CODER_UNIT"
else
  systemctl start "$CODER_UNIT"
fi

if systemctl is-active --quiet "$ROUTER_UNIT"; then
  systemctl reload "$ROUTER_UNIT"
else
  systemctl start "$ROUTER_UNIT"
fi

assert_oneshot_active() {
  local unit="$1"
  local active sub status
  active="$(systemctl show "$unit" -p ActiveState --value)"
  sub="$(systemctl show "$unit" -p SubState --value)"
  status="$(systemctl show "$unit" -p ExecMainStatus --value)"
  if [[ "$active" != active || "$sub" != exited || "$status" != 0 ]]; then
    echo "$unit не подтвердил active/exited/0: $active/$sub/$status" >&2
    return 1
  fi
}

assert_oneshot_active "$CODER_UNIT"
assert_oneshot_active "$ROUTER_UNIT"

HERMES_CODERS_ROOT="$HERMES_ROOT" \
HERMES_CODEX_STRICT_NESTED_PROC_SMOKE=0 \
  python3 "$coder_dir/runtime_smoke.py"
HERMES_CODERS_ROOT="$HERMES_ROOT" \
  python3 "$coder_dir/tier_provider_smoke.py"
HERMES_CODER_ROUTER_ENV_FILE=/srv/hermes-operator-control/coders.env \
  python3 "$router_dir/router_smoke.py"

for container in \
  hermes-coders-hermes-coder-velvet-1 \
  hermes-coders-hermes-coder-max-1; do
  test "$(docker inspect "$container" --format '{{.State.Status}}')" = running
  test "$(docker inspect "$container" --format '{{.State.Health.Status}}')" = healthy
  test "$(docker inspect "$container" --format '{{.RestartCount}}')" -eq 0
  test "$(docker inspect "$container" --format '{{json .HostConfig.Init}}')" = true
done

# Retire, rather than erase, the old manual override after the canonical path passes.
if [[ -e "$LEGACY_OVERRIDE" || -L "$LEGACY_OVERRIDE" ]]; then
  mv -- "$LEGACY_OVERRIDE" "$backup_dir/compose.bwrap.override.retired.yaml"
fi

trap - ERR INT TERM
printf '%s\n' \
  "Hermes release systemd reconciliation: OK" \
  "Release SHA: $release_sha" \
  "Backup: $backup_dir" \
  "$CODER_UNIT: active/exited/0" \
  "$ROUTER_UNIT: active/exited/0"
