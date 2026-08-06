#!/usr/bin/env bash
set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 022

readonly TARGET_SHA="${1:-}"
readonly APP_USER=velvet
readonly APP_DIR=/srv/velvet
readonly HERMES_ROOT=/srv/hermes-coders
readonly RELEASE_ROOT="$HERMES_ROOT/releases"
readonly MIRROR_ROOT=/var/lib/hermes-coders-release
readonly MIRROR_REPO="$MIRROR_ROOT/repository.git"
readonly REPOSITORY_URL=https://github.com/Stellmaria/Velvet.git
readonly LOCK_DIR=/run/lock/hermes-coders

abort() {
  echo "Hermes release runner refused: $*" >&2
  exit 2
}

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  abort "root execution is required"
fi
if [[ "$#" -ne 1 || ! "$TARGET_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  abort "exactly one lowercase 40-character SHA is required"
fi
if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != "$APP_USER" ]]; then
  abort "unexpected sudo caller: $SUDO_USER"
fi
if [[ ! -d "$APP_DIR/.git" ]]; then
  abort "production checkout is missing: $APP_DIR"
fi

install -d -o root -g root -m 0755 \
  "$MIRROR_ROOT" \
  "$RELEASE_ROOT" \
  "$LOCK_DIR"

if [[ -e "$MIRROR_REPO" && ! -d "$MIRROR_REPO/objects" ]]; then
  abort "release mirror path is not a bare Git repository"
fi
if [[ ! -d "$MIRROR_REPO/objects" ]]; then
  git init --bare "$MIRROR_REPO"
  git -C "$MIRROR_REPO" remote add origin "$REPOSITORY_URL"
else
  git -C "$MIRROR_REPO" remote set-url origin "$REPOSITORY_URL"
fi

if find "$MIRROR_ROOT" -xdev ! -user root -print -quit | grep -q .; then
  abort "release mirror contains non-root-owned paths"
fi

git -C "$MIRROR_REPO" fetch \
  --no-tags \
  --prune \
  --force \
  origin \
  refs/heads/main:refs/remotes/origin/main

remote_main="$(git -C "$MIRROR_REPO" rev-parse refs/remotes/origin/main)"
if [[ "$remote_main" != "$TARGET_SHA" ]]; then
  abort "target is no longer current main: $TARGET_SHA != $remote_main"
fi
git -C "$MIRROR_REPO" cat-file -e "${TARGET_SHA}^{commit}"

release_dir="$RELEASE_ROOT/$TARGET_SHA"
if [[ -e "$release_dir" ]]; then
  if [[ -L "$release_dir" || ! -d "$release_dir" ]]; then
    abort "release path is not a regular directory: $release_dir"
  fi
  if [[ "$(stat -c '%U:%G' "$release_dir")" != "root:root" ]]; then
    abort "existing release worktree is not root-owned: $release_dir"
  fi
  if [[ "$(git -C "$release_dir" rev-parse HEAD)" != "$TARGET_SHA" ]]; then
    abort "existing release worktree has the wrong commit"
  fi
  git -C "$release_dir" diff --quiet
  git -C "$release_dir" diff --cached --quiet
  if [[ -n "$(git -C "$release_dir" ls-files --others --exclude-standard)" ]]; then
    abort "existing release worktree contains untracked files"
  fi
else
  git -C "$MIRROR_REPO" worktree prune
  git -C "$MIRROR_REPO" worktree add --detach "$release_dir" "$TARGET_SHA"
fi

if find "$release_dir" -xdev ! -user root -print -quit | grep -q .; then
  abort "release worktree contains non-root-owned paths"
fi

release_script="$release_dir/deploy/hermes-coders/release.sh"
if [[ ! -x "$release_script" || -L "$release_script" ]]; then
  abort "versioned release script is missing or unsafe"
fi

exec /usr/bin/env -i \
  PATH="$PATH" \
  HOME=/root \
  USER=root \
  LOGNAME=root \
  LANG=C.UTF-8 \
  LC_ALL=C.UTF-8 \
  TMPDIR="$LOCK_DIR" \
  HERMES_RELEASE_ROOT="$release_dir" \
  HERMES_CODERS_ROOT="$HERMES_ROOT" \
  HERMES_CODERS_APP_USER="$APP_USER" \
  "$release_script" "$TARGET_SHA" "$APP_DIR"
