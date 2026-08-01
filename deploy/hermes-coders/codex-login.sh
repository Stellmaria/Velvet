#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите через sudo." >&2
  exit 1
fi

project="${1:-}"
case "$project" in
  velvet|max) ;;
  *)
    echo "Использование: sudo bash deploy/hermes-coders/codex-login.sh velvet|max" >&2
    exit 2
    ;;
esac

ROOT="${HERMES_CODERS_ROOT:-/srv/hermes-coders}"
SOURCE_DIR="${HERMES_CODERS_SOURCE_DIR:-/srv/velvet/deploy/hermes-coders}"
SERVICE_USER="${HERMES_CODERS_APP_USER:-velvet}"
service="hermes-coder-$project"

if [[ ! -f "$SOURCE_DIR/compose.yaml" ]]; then
  echo "Не найден Compose-файл: $SOURCE_DIR/compose.yaml" >&2
  exit 3
fi
if [[ ! -d "$ROOT/codex/$project" ]]; then
  echo "Не найден CODEX_HOME: $ROOT/codex/$project. Сначала выполните install.sh." >&2
  exit 3
fi

cd "$SOURCE_DIR"
runuser -u "$SERVICE_USER" -- env \
  HERMES_CODERS_ROOT="$ROOT" \
  docker compose --profile "$project" -f compose.yaml build "$service"

cat <<EOF

Сейчас Codex покажет ссылку и одноразовый код.
Откройте ссылку в браузере, войдите в нужный ChatGPT-аккаунт и введите код.
Для headless VPS должен быть включён Device Code authorization в настройках безопасности ChatGPT.

EOF

runuser -u "$SERVICE_USER" -- env \
  HERMES_CODERS_ROOT="$ROOT" \
  docker compose --profile "$project" -f compose.yaml run --rm --no-deps \
  --entrypoint codex "$service" login --device-auth

if [[ ! -s "$ROOT/codex/$project/auth.json" ]]; then
  echo "Codex сообщил о завершении, но auth.json не создан: $ROOT/codex/$project/auth.json" >&2
  exit 4
fi
chmod 0600 "$ROOT/codex/$project/auth.json"
chown "$(stat -c '%u' "$ROOT/codex/$project")":"$(stat -c '%g' "$ROOT/codex/$project")" \
  "$ROOT/codex/$project/auth.json"

echo "Codex $project авторизован. Проверка статуса:"
runuser -u "$SERVICE_USER" -- env \
  HERMES_CODERS_ROOT="$ROOT" \
  docker compose --profile "$project" -f compose.yaml run --rm --no-deps \
  --entrypoint codex "$service" login status
