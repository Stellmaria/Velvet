#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите через sudo." >&2
  exit 1
fi

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SOURCE_DIR="${HERMES_CODERS_SOURCE_DIR:-$SCRIPT_DIR}"
REPO_ROOT="${HERMES_RELEASE_ROOT:-$(cd "$SOURCE_DIR/../.." && pwd -P)}"
APP_USER="${HERMES_CODERS_APP_USER:-velvet}"
APP_GROUP="${HERMES_CODERS_APP_GROUP:-velvet}"
ROOT="${HERMES_CODERS_ROOT:-/srv/hermes-coders}"
BRAIN_SOURCE="${HERMES_BRAIN_SOURCE_DIR:-$REPO_ROOT/deploy/hermes-brain}"
BRAIN_VAULT_MANIFEST="${HERMES_BRAIN_MANIFEST:-$REPO_ROOT/brain-vault/manifest.json}"
OPERATOR_ENV="${HERMES_OPERATOR_ENV:-/srv/velvet/.env.hermes}"
CONTROL_OPERATOR_ENV="${HERMES_CONTROL_OPERATOR_ENV:-/srv/hermes-operator-control/operator.env}"
VELVET_REPO="${HERMES_VELVET_REPO:-https://github.com/Stellmaria/Velvet.git}"
MAX_REPO="${HERMES_MAX_REPO:-https://github.com/Stellmaria/romatic_club_bot_max.git}"
HERMES_UID_VALUE="${HERMES_UID:-10000}"
HERMES_GID_VALUE="${HERMES_GID:-10000}"
UNIT_SOURCE="$REPO_ROOT/deploy/systemd/hermes-coders.service"
UNIT_TARGET="/etc/systemd/system/hermes-coders.service"
LAUNCHER_INSTALLER="$REPO_ROOT/deploy/hermes-sandbox-launcher/install.sh"
RELEASE_ROOT="$ROOT/releases"
CURRENT_LINK="$RELEASE_ROOT/current-hermes-coders"
LAUNCHER_ENV="$ROOT/launcher.env"
LAUNCHER_SECRETS="$ROOT/launcher-secrets.env"

for value in "$SOURCE_DIR" "$REPO_ROOT" "$BRAIN_SOURCE"; do
  if [[ "$value" != /* ]]; then
    echo "Canonical installer paths должны быть абсолютными: $value" >&2
    exit 2
  fi
done

for required in \
  "$SOURCE_DIR/compose.yaml" \
  "$SOURCE_DIR/compose.runtime.yaml" \
  "$SOURCE_DIR/compose.security.yaml" \
  "$SOURCE_DIR/config.yaml" \
  "$SOURCE_DIR/SOUL.velvet.md" \
  "$SOURCE_DIR/SOUL.max.md" \
  "$SOURCE_DIR/ensure_runtime_config.py" \
  "$SOURCE_DIR/ensure_idle.py" \
  "$SOURCE_DIR/ensure_launcher_tokens.py" \
  "$SOURCE_DIR/pin_launcher_images.py" \
  "$SOURCE_DIR/preflight.py" \
  "$SOURCE_DIR/sandbox_preflight.py" \
  "$SOURCE_DIR/runtime_smoke.py" \
  "$SOURCE_DIR/runtime_source_guard.py" \
  "$SOURCE_DIR/security/apparmor-hermes-codex-runner" \
  "$SOURCE_DIR/security/apparmor-hermes-codex-run" \
  "$BRAIN_SOURCE/context_compiler.py" \
  "$BRAIN_SOURCE/install_context_pack.py" \
  "$BRAIN_SOURCE/verify_installed_context.py" \
  "$BRAIN_VAULT_MANIFEST" \
  "$OPERATOR_ENV" \
  "$CONTROL_OPERATOR_ENV" \
  "$UNIT_SOURCE" \
  "$LAUNCHER_INSTALLER"; do
  if [[ ! -f "$required" || -L "$required" ]]; then
    echo "Отсутствует или небезопасен обязательный файл: $required" >&2
    exit 2
  fi
done

# Security/runtime activation is forbidden while any ledger run or canonical
# disposable container remains active.
HERMES_CODERS_ROOT="$ROOT" python3 "$SOURCE_DIR/ensure_idle.py"

pack_root="$(mktemp -d)"
trap 'rm -rf -- "$pack_root"' EXIT
python3 "$BRAIN_SOURCE/context_compiler.py" validate
for entity in velvet-coder max-coder; do
  python3 "$BRAIN_SOURCE/context_compiler.py" compile \
    --entity "$entity" \
    --output "$pack_root/$entity"
done

install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 \
  "$ROOT" \
  "$ROOT/workspaces" \
  "$RELEASE_ROOT"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0700 "$ROOT/secrets"
install -d -o "$HERMES_UID_VALUE" -g "$APP_GROUP" -m 0750 \
  "$ROOT/data" \
  "$ROOT/data/velvet" \
  "$ROOT/data/max"

clone_workspace() {
  local repo_url="$1"
  local target="$2"
  if [[ -d "$target/.git" ]]; then
    echo "Workspace уже существует: $target"
    return
  fi
  if [[ -e "$target" ]] && [[ -n "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    echo "Каталог workspace не пуст и не является Git checkout: $target" >&2
    exit 3
  fi
  rm -rf -- "$target"
  runuser -u "$APP_USER" -- git clone --filter=blob:none "$repo_url" "$target"
  chown -R "$HERMES_UID_VALUE:$HERMES_GID_VALUE" "$target"
}

clone_workspace "$VELVET_REPO" "$ROOT/workspaces/velvet"
clone_workspace "$MAX_REPO" "$ROOT/workspaces/max"

python3 - "$OPERATOR_ENV" "$CONTROL_OPERATOR_ENV" "$ROOT/secrets/velvet.env" "$ROOT/secrets/max.env" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def write_env(path: Path, model_values: dict[str, str]) -> None:
    existing = parse_env(path)
    api_key = existing.get("API_SERVER_KEY", "")
    runner_key = existing.get("CODEX_RUNNER_API_KEY", "") or api_key
    values = {
        # The operator credential is canonical when present so normal install
        # propagates an intentional rotation to both project-scoped env files.
        # Preserve the existing key only when operator config supplies none.
        "BYESU_HERMES_CODEX_API_KEY": (
            model_values["BYESU_HERMES_CODEX_API_KEY"]
            or existing.get("BYESU_HERMES_CODEX_API_KEY", "")
        ),
        "TELEGRAM_BOT_TOKEN": existing.get("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_ALLOWED_USERS": existing.get("TELEGRAM_ALLOWED_USERS", ""),
        "GH_TOKEN": existing.get("GH_TOKEN", ""),
        "API_SERVER_KEY": api_key,
        "CODEX_RUNNER_API_KEY": runner_key,
        "HERMES_CODER_ROUTER_CLIENT_TOKEN": (
            existing.get("HERMES_CODER_ROUTER_CLIENT_TOKEN", "")
            or model_values["HERMES_CODER_ROUTER_CLIENT_TOKEN"]
        ),
        # Preserve an existing project-scoped launcher token. The dedicated
        # helper validates or creates it atomically after this write.
        "HERMES_SANDBOX_LAUNCHER_TOKEN": existing.get(
            "HERMES_SANDBOX_LAUNCHER_TOKEN", ""
        ),
    }
    body = "\n".join(
        f"{key}={value}"
        for key, value in values.items()
        if value or key != "HERMES_SANDBOX_LAUNCHER_TOKEN"
    ) + "\n"
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o600)


source = parse_env(Path(sys.argv[1]))
operator = parse_env(Path(sys.argv[2]))
model_values = {
    "BYESU_HERMES_CODEX_API_KEY": (
        source.get("BYESU_HERMES_CODEX_API_KEY", "")
        or source.get("BYESU_HERMES_API_KEY", "")
        or source.get("OPENAI_API_KEY", "")
    ),
    "HERMES_CODER_ROUTER_CLIENT_TOKEN": operator.get("HERMES_OPS_CLIENT_TOKEN", ""),
}
if len(model_values["HERMES_CODER_ROUTER_CLIENT_TOKEN"]) < 24:
    raise SystemExit("Canonical coder router client token отсутствует или слишком короткий")
for target in map(Path, sys.argv[3:]):
    write_env(target, model_values)
PY

for project in velvet max; do
  data_dir="$ROOT/data/$project"
  if [[ ! -f "$data_dir/config.yaml" ]]; then
    install -o "$HERMES_UID_VALUE" -g "$APP_GROUP" -m 0640 \
      "$SOURCE_DIR/config.yaml" "$data_dir/config.yaml"
  fi
  if [[ ! -f "$data_dir/SOUL.md" ]]; then
    install -o "$HERMES_UID_VALUE" -g "$APP_GROUP" -m 0640 \
      "$SOURCE_DIR/SOUL.$project.md" "$data_dir/SOUL.md"
  fi
  chown "$HERMES_UID_VALUE:$APP_GROUP" "$data_dir/config.yaml" "$data_dir/SOUL.md"
  chmod 0640 "$data_dir/config.yaml" "$data_dir/SOUL.md"
done

python3 "$SOURCE_DIR/ensure_runtime_config.py" \
  "$ROOT/data/velvet/config.yaml" \
  "$ROOT/data/max/config.yaml"

for project in velvet max; do
  entity="$project-coder"
  python3 "$BRAIN_SOURCE/install_context_pack.py" \
    --pack "$pack_root/$entity" \
    --target "$ROOT/data/$project" \
    --entity "$entity" \
    --mode hermes
  python3 "$BRAIN_SOURCE/verify_installed_context.py" \
    --target "$ROOT/data/$project" \
    --entity "$entity" \
    --mode hermes
  if [[ -d "$ROOT/codex/$project" ]]; then
    python3 "$BRAIN_SOURCE/install_context_pack.py" \
      --pack "$pack_root/$entity" \
      --target "$ROOT/codex/$project" \
      --entity "$entity" \
      --mode codex
    python3 "$BRAIN_SOURCE/verify_installed_context.py" \
      --target "$ROOT/codex/$project" \
      --entity "$entity" \
      --mode codex
  fi
done

for project in velvet max; do
  gitconfig="$ROOT/data/$project/.gitconfig"
  display_name="Hermes ${project^} Coder"
  email="hermes-$project@users.noreply.github.com"
  cat > "$gitconfig" <<EOF
[user]
    name = $display_name
    email = $email
[credential "https://github.com"]
    helper = !gh auth git-credential
[safe]
    directory = /workspace
EOF
  chown "$HERMES_UID_VALUE:$APP_GROUP" "$gitconfig"
  chmod 0640 "$gitconfig"
done

chmod 0600 "$ROOT/secrets/velvet.env" "$ROOT/secrets/max.env"
chown "$APP_USER:$APP_GROUP" "$ROOT/secrets/velvet.env" "$ROOT/secrets/max.env"
for db_env in "$ROOT/secrets/velvet-db.env" "$ROOT/secrets/max-db.env"; do
  if [[ ! -f "$db_env" ]]; then
    echo "Отсутствует ранее подготовленный read-only DB env: $db_env" >&2
    exit 4
  fi
  chown "$APP_USER:$APP_GROUP" "$db_env"
  chmod 0600 "$db_env"
done

# Generate two distinct project tokens. Each runner receives only its own token
# through its existing project env_file; the root launcher receives only this
# two-token root-owned projection.
python3 "$SOURCE_DIR/ensure_launcher_tokens.py" \
  "$ROOT/secrets/velvet.env" \
  "$ROOT/secrets/max.env" \
  "$LAUNCHER_SECRETS"
chown root:root "$LAUNCHER_SECRETS"
chmod 0600 "$LAUNCHER_SECRETS"

# Stage exact launcher code, units and AppArmor without switching current or
# starting the launcher. Traffic remains on the previous release.
HERMES_RELEASE_ROOT="$REPO_ROOT" \
HERMES_CODERS_SOURCE_DIR="$SOURCE_DIR" \
HERMES_CODERS_ROOT="$ROOT" \
HERMES_CODERS_APP_GROUP="$APP_GROUP" \
HERMES_UID="$HERMES_UID_VALUE" \
HERMES_GID="$HERMES_GID_VALUE" \
  "$LAUNCHER_INSTALLER"

install -o root -g root -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"

set -a
# shellcheck disable=SC1090
source "$LAUNCHER_ENV"
set +a
cd "$SOURCE_DIR"
compose=(
  docker compose
  --project-name hermes-coders
  --profile velvet
  --profile max
  -f compose.yaml
  -f compose.runtime.yaml
  -f compose.security.yaml
)
HERMES_CODERS_ROOT="$ROOT" "${compose[@]}" config --quiet
HERMES_CODERS_ROOT="$ROOT" "${compose[@]}" build

velvet_image="$(
  docker image inspect velvet-codex-coder-velvet:local --format '{{.Id}}'
)"
max_image="$(
  docker image inspect velvet-codex-coder-max:local --format '{{.Id}}'
)"
for image in "$velvet_image" "$max_image"; do
  if [[ ! "$image" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "Compose build не дал immutable Docker image ID: $image" >&2
    exit 5
  fi
done

# Atomically record both immutable IDs and switch launcher current to the
# exact staged release. The helper restores the previous symlink if env
# replacement fails.
python3 "$SOURCE_DIR/pin_launcher_images.py" \
  "$LAUNCHER_ENV" \
  "$velvet_image" \
  "$max_image"

systemctl daemon-reload
systemctl enable --now hermes-sandbox-launcher.socket
systemctl restart hermes-sandbox-launcher.service
test "$(systemctl is-active hermes-sandbox-launcher.service)" = active

HERMES_CODERS_ROOT="$ROOT" python3 "$SOURCE_DIR/preflight.py"
HERMES_CODERS_ROOT="$ROOT" python3 "$SOURCE_DIR/sandbox_preflight.py"

# Switch coder traffic only after authenticated Velvet/Max launcher probes pass.
link_tmp="$RELEASE_ROOT/.current-hermes-coders.$$"
ln -s "$REPO_ROOT" "$link_tmp"
mv -Tf "$link_tmp" "$CURRENT_LINK"

systemctl enable hermes-coders.service
systemctl restart hermes-coders.service
active_state="$(systemctl show hermes-coders.service -p ActiveState --value)"
sub_state="$(systemctl show hermes-coders.service -p SubState --value)"
exec_status="$(systemctl show hermes-coders.service -p ExecMainStatus --value)"
if [[ "$active_state" != "active" || "$sub_state" != "exited" || "$exec_status" != "0" ]]; then
  echo "hermes-coders.service не подтвердил active/exited/0: $active_state/$sub_state/$exec_status" >&2
  exit 6
fi

printf '%s\n' \
  "Hermes Coder canonical infrastructure activated." \
  "- release root: $REPO_ROOT" \
  "- current coder link: $CURRENT_LINK" \
  "- launcher current: $(readlink -f /usr/local/lib/hermes-sandbox-launcher/current)" \
  "- execution backend: host-sandbox-launcher" \
  "- immutable Velvet image: $velvet_image" \
  "- immutable Max image: $max_image" \
  "- compatibility override: not used"
