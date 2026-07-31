#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите через sudo." >&2
  exit 1
fi

APP_USER="${HERMES_CODERS_APP_USER:-velvet}"
APP_GROUP="${HERMES_CODERS_APP_GROUP:-velvet}"
ROOT="${HERMES_CODERS_ROOT:-/srv/hermes-coders}"
SOURCE_DIR="${HERMES_CODERS_SOURCE_DIR:-/srv/velvet/deploy/hermes-coders}"
OPERATOR_ENV="${HERMES_OPERATOR_ENV:-/srv/velvet/.env.hermes}"
VELVET_REPO="${HERMES_VELVET_REPO:-https://github.com/Stellmaria/Velvet.git}"
MAX_REPO="${HERMES_MAX_REPO:-https://github.com/Stellmaria/romatic_club_bot_max.git}"
HERMES_UID_VALUE="${HERMES_UID:-10000}"
HERMES_GID_VALUE="${HERMES_GID:-10000}"
UNIT_SOURCE="/srv/velvet/deploy/systemd/hermes-coders.service"
UNIT_TARGET="/etc/systemd/system/hermes-coders.service"

for required in \
  "$SOURCE_DIR/compose.yaml" \
  "$SOURCE_DIR/config.yaml" \
  "$SOURCE_DIR/SOUL.velvet.md" \
  "$SOURCE_DIR/SOUL.max.md" \
  "$SOURCE_DIR/preflight.py" \
  "$OPERATOR_ENV" \
  "$UNIT_SOURCE"; do
  if [[ ! -f "$required" ]]; then
    echo "Отсутствует обязательный файл: $required" >&2
    exit 2
  fi
done

install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$ROOT"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0700 "$ROOT/secrets"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$ROOT/workspaces"
install -d -o "$HERMES_UID_VALUE" -g "$HERMES_GID_VALUE" -m 0750 \
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

  rm -rf "$target"
  runuser -u "$APP_USER" -- git clone --filter=blob:none "$repo_url" "$target"
  chown -R "$HERMES_UID_VALUE:$HERMES_GID_VALUE" "$target"
}

clone_workspace "$VELVET_REPO" "$ROOT/workspaces/velvet"
clone_workspace "$MAX_REPO" "$ROOT/workspaces/max"

python3 - "$OPERATOR_ENV" "$ROOT/secrets/velvet.env" "$ROOT/secrets/max.env" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def write_env(path: Path, model_values: dict[str, str]) -> None:
    existing = parse_env(path) if path.exists() else {}
    values = {
        "BYESU_HERMES_CODEX_API_KEY": model_values["BYESU_HERMES_CODEX_API_KEY"],
        "BYESU_HERMES_GPT_PRO_API_KEY": model_values["BYESU_HERMES_GPT_PRO_API_KEY"],
        "TELEGRAM_BOT_TOKEN": existing.get("TELEGRAM_BOT_TOKEN", ""),
        "TELEGRAM_ALLOWED_USERS": existing.get("TELEGRAM_ALLOWED_USERS", ""),
        "GH_TOKEN": existing.get("GH_TOKEN", ""),
    }
    body = "\n".join(f"{key}={value}" for key, value in values.items()) + "\n"
    path.write_text(body, encoding="utf-8")
    os.chmod(path, 0o600)


source = parse_env(Path(sys.argv[1]))
coder_key = source.get("BYESU_HERMES_CODEX_API_KEY", "")
pro_key = (
    source.get("BYESU_HERMES_GPT_PRO_API_KEY", "")
    or source.get("BYESU_HERMES_API_KEY", "")
    or source.get("OPENAI_API_KEY", "")
)
if not coder_key:
    raise SystemExit("В operator env отсутствует BYESU_HERMES_CODEX_API_KEY")
if not pro_key:
    raise SystemExit("В operator env не найден ключ маршрута gpt-5.6-luna")

model_values = {
    "BYESU_HERMES_CODEX_API_KEY": coder_key,
    "BYESU_HERMES_GPT_PRO_API_KEY": pro_key,
}
for target in map(Path, sys.argv[2:]):
    write_env(target, model_values)
PY

for project in velvet max; do
  data_dir="$ROOT/data/$project"
  if [[ ! -f "$data_dir/config.yaml" ]]; then
    install -o "$HERMES_UID_VALUE" -g "$HERMES_GID_VALUE" -m 0600 \
      "$SOURCE_DIR/config.yaml" "$data_dir/config.yaml"
  fi

  if [[ ! -f "$data_dir/SOUL.md" ]]; then
    install -o "$HERMES_UID_VALUE" -g "$HERMES_GID_VALUE" -m 0600 \
      "$SOURCE_DIR/SOUL.$project.md" "$data_dir/SOUL.md"
  fi
done

cat > "$ROOT/data/velvet/.gitconfig" <<'EOF'
[user]
    name = Hermes Velvet Coder
    email = hermes-velvet@users.noreply.github.com
[credential "https://github.com"]
    helper = !gh auth git-credential
[safe]
    directory = /workspace
EOF

cat > "$ROOT/data/max/.gitconfig" <<'EOF'
[user]
    name = Hermes Max Coder
    email = hermes-max@users.noreply.github.com
[credential "https://github.com"]
    helper = !gh auth git-credential
[safe]
    directory = /workspace
EOF

chown "$HERMES_UID_VALUE:$HERMES_GID_VALUE" \
  "$ROOT/data/velvet/.gitconfig" \
  "$ROOT/data/max/.gitconfig"
chmod 0600 \
  "$ROOT/data/velvet/.gitconfig" \
  "$ROOT/data/max/.gitconfig"
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

install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
systemctl daemon-reload

cd "$SOURCE_DIR"
HERMES_CODERS_ROOT="$ROOT" docker compose \
  --profile velvet \
  --profile max \
  -f compose.yaml \
  config --quiet

HERMES_CODERS_ROOT="$ROOT" docker compose \
  --profile velvet \
  --profile max \
  -f compose.yaml \
  build

cat <<EOF

Hermes Coder infrastructure prepared.

Не запущено намеренно: сначала заполните два разных Telegram bot token
и два разных fine-grained GitHub token в:
  $ROOT/secrets/velvet.env
  $ROOT/secrets/max.env

Затем:
  sudo -u $APP_USER HERMES_CODERS_ROOT=$ROOT python3 $SOURCE_DIR/preflight.py
  sudo systemctl enable --now hermes-coders.service
EOF
