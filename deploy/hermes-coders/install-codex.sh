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
VELVET_REPO="${HERMES_VELVET_REPO:-https://github.com/Stellmaria/Velvet.git}"
MAX_REPO="${HERMES_MAX_REPO:-https://github.com/Stellmaria/romatic_club_bot_max.git}"
HERMES_UID_VALUE="${HERMES_UID:-10000}"
HERMES_GID_VALUE="${HERMES_GID:-10000}"

for required in \
  "$SOURCE_DIR/compose.yaml" \
  "$SOURCE_DIR/Dockerfile.coder" \
  "$SOURCE_DIR/codex_runner.py" \
  "$SOURCE_DIR/codex-login.sh" \
  "$ROOT/secrets/velvet.env" \
  "$ROOT/secrets/max.env"; do
  if [[ ! -f "$required" ]]; then
    echo "Отсутствует обязательный файл: $required" >&2
    exit 2
  fi
done

install -d -o "$HERMES_UID_VALUE" -g "$APP_GROUP" -m 0750 \
  "$ROOT/codex" \
  "$ROOT/codex/velvet" \
  "$ROOT/codex/max"
install -d -o "$HERMES_UID_VALUE" -g "$HERMES_GID_VALUE" -m 0750 \
  "$ROOT/codex-runs" \
  "$ROOT/codex-runs/velvet" \
  "$ROOT/codex-runs/max"
install -d -o "$APP_USER" -g "$APP_GROUP" -m 0750 "$ROOT/workspaces"

clone_workspace() {
  local repo_url="$1"
  local target="$2"
  local git_name="$3"
  local git_email="$4"

  if [[ -d "$target/.git" ]]; then
    echo "Codex workspace уже существует: $target"
    chown -R "$APP_USER:$APP_GROUP" "$target"
  else
    if [[ -e "$target" ]] && [[ -n "$(find "$target" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
      echo "Каталог не пуст и не является Git checkout: $target" >&2
      exit 3
    fi
    rm -rf "$target"
    runuser -u "$APP_USER" -- git clone --filter=blob:none "$repo_url" "$target"
  fi
  runuser -u "$APP_USER" -- git -C "$target" config user.name "$git_name"
  runuser -u "$APP_USER" -- git -C "$target" config user.email "$git_email"
  runuser -u "$APP_USER" -- git -C "$target" config \
    credential.https://github.com.helper '!gh auth git-credential'
  chown -R "$HERMES_UID_VALUE:$HERMES_GID_VALUE" "$target"
}

clone_workspace \
  "$VELVET_REPO" \
  "$ROOT/workspaces/velvet-codex" \
  "Codex Velvet Coder" \
  "codex-velvet@users.noreply.github.com"
clone_workspace \
  "$MAX_REPO" \
  "$ROOT/workspaces/max-codex" \
  "Codex Max Coder" \
  "codex-max@users.noreply.github.com"

python3 - "$ROOT/secrets/velvet.env" "$ROOT/secrets/max.env" <<'PY'
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path


def parse(path: Path) -> tuple[list[str], dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return lines, values


def write(path: Path) -> str:
    lines, values = parse(path)
    api_key = values.get("API_SERVER_KEY", "")
    if len(api_key) < 24:
        api_key = secrets.token_urlsafe(48)
    runner_key = api_key
    replacements = {
        "API_SERVER_KEY": api_key,
        "CODEX_RUNNER_API_KEY": runner_key,
    }
    seen: set[str] = set()
    output: list[str] = []
    for raw in lines:
        stripped = raw.strip()
        key = stripped.split("=", 1)[0].removeprefix("export ").strip() if "=" in stripped else ""
        if key in replacements:
            output.append(f"{key}={replacements[key]}")
            seen.add(key)
        else:
            output.append(raw)
    if output and output[-1].strip():
        output.append("")
    if "CODEX_RUNNER_API_KEY" not in seen:
        output.extend(("# OpenAI Codex local runner", f"CODEX_RUNNER_API_KEY={runner_key}"))
    if "API_SERVER_KEY" not in seen:
        output.append(f"API_SERVER_KEY={api_key}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    os.chmod(path, 0o600)
    return runner_key


keys = [write(Path(arg)) for arg in sys.argv[1:]]
if keys[0] == keys[1]:
    raise SystemExit("Velvet и Max CODEX_RUNNER_API_KEY должны различаться")
print("Codex runner keys подготовлены без вывода значений.")
PY

for project in velvet max; do
  codex_home="$ROOT/codex/$project"
  cat > "$codex_home/config.toml" <<'EOF'
model = "gpt-5.6-terra"
sandbox_mode = "workspace-write"
approval_policy = "never"
cli_auth_credentials_store = "file"
check_for_update_on_startup = false

[sandbox_workspace_write]
network_access = true

[shell_environment_policy]
ignore_default_excludes = true
exclude = [
  "API_SERVER_KEY",
  "BYESU_HERMES_CODEX_API_KEY",
  "BYESU_HERMES_GPT_PRO_API_KEY",
  "CODEX_RUNNER_API_KEY",
  "DATABASE_URL",
  "PGPASSWORD",
  "TELEGRAM_BOT_TOKEN",
]

[features]
apps = false
plugins = false
tool_suggest = false
EOF
  chown "$HERMES_UID_VALUE:$HERMES_GID_VALUE" "$codex_home/config.toml"
  chmod 0600 "$codex_home/config.toml"
done

chmod 0600 "$ROOT/secrets/velvet.env" "$ROOT/secrets/max.env"
chown "$APP_USER:$APP_GROUP" "$ROOT/secrets/velvet.env" "$ROOT/secrets/max.env"
chmod 0755 "$SOURCE_DIR/codex-login.sh"

cd "$SOURCE_DIR"
runuser -u "$APP_USER" -- env HERMES_CODERS_ROOT="$ROOT" \
  docker compose --profile velvet --profile max -f compose.yaml config --quiet
runuser -u "$APP_USER" -- env HERMES_CODERS_ROOT="$ROOT" \
  docker compose --profile velvet --profile max -f compose.yaml \
  build hermes-coder-velvet hermes-coder-max

cat <<EOF

Codex runner infrastructure prepared, но runner ещё не запускается без входа.
Выполните последовательно:

  sudo bash $SOURCE_DIR/codex-login.sh velvet
  sudo bash $SOURCE_DIR/codex-login.sh max
  sudo env HERMES_CODERS_ROOT=$ROOT python3 $SOURCE_DIR/preflight.py
  sudo systemctl restart hermes-coders.service
  sudo systemctl restart hermes-coder-router.service

EOF
