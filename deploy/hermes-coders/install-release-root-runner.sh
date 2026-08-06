#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Release runner installation requires root." >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCE="${HERMES_RELEASE_RUNNER_SOURCE:-$SCRIPT_DIR/release-root-runner.sh}"
APP_USER="${HERMES_CODERS_APP_USER:-velvet}"
RUNNER_TARGET=/usr/local/sbin/hermes-coders-release
SUDOERS_TARGET=/etc/sudoers.d/hermes-coders-release

if [[ ! "$APP_USER" =~ ^[a-z_][a-z0-9_-]*$ ]] || ! id "$APP_USER" >/dev/null 2>&1; then
  echo "Invalid Hermes deployment user: $APP_USER" >&2
  exit 2
fi
if [[ ! -f "$SOURCE" || -L "$SOURCE" ]]; then
  echo "Release runner source is missing or unsafe: $SOURCE" >&2
  exit 2
fi
if ! command -v visudo >/dev/null 2>&1; then
  echo "visudo is required to install the bounded release command." >&2
  exit 2
fi

install -d -o root -g root -m 0755 /usr/local/sbin /etc/sudoers.d
install -o root -g root -m 0755 "$SOURCE" "$RUNNER_TARGET"

sudoers_tmp="$(mktemp /etc/sudoers.d/.hermes-coders-release.XXXXXX)"
trap 'rm -f -- "$sudoers_tmp"' EXIT
cat > "$sudoers_tmp" <<EOF
Cmnd_Alias HERMES_CODERS_RELEASE = $RUNNER_TARGET
$APP_USER ALL=(root) NOPASSWD: HERMES_CODERS_RELEASE
EOF
chown root:root "$sudoers_tmp"
chmod 0440 "$sudoers_tmp"
visudo -cf "$sudoers_tmp"
install -o root -g root -m 0440 "$sudoers_tmp" "$SUDOERS_TARGET"
visudo -cf "$SUDOERS_TARGET"

printf '%s\n' \
  "Hermes release runner installed." \
  "- runner: $RUNNER_TARGET" \
  "- sudoers: $SUDOERS_TARGET" \
  "- caller: $APP_USER" \
  "- privilege: exact root-owned runner only"
