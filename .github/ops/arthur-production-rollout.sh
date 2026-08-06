#!/usr/bin/env bash
# Merge-triggered CI marker for the one-time Arthur production rollout.
set -Eeuo pipefail
umask 077
trap 'rm -f -- "$SECRET_FILE"' EXIT
cd "$APP_DIR"

test -n "$SOURCE_COMMIT"
test -n "$CHECKOUT_COMMIT"
test -f "$SECRET_FILE"
chmod 600 "$SECRET_FILE"
test -f "$APP_DIR/.env.server"
test "$(git symbolic-ref --short HEAD)" = main
test -z "$(git status --porcelain --untracked-files=all)"

python3 - "$APP_DIR/.env.server" "$SECRET_FILE" <<'PY'
from __future__ import annotations

import hmac
import json
import os
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
secret_path = Path(sys.argv[2])
payload = json.loads(secret_path.read_text(encoding="utf-8"))
if not isinstance(payload, dict):
    raise SystemExit("Arthur credential payload is invalid")

names = (
    "ARTHUR_BOT_TOKEN",
    "ARTHUR_ALLOWED_USER_IDS",
    "ARTHUR_ALLOWED_USERNAMES",
    "ARTHUR_STORAGE_GATEWAY_API_KEY",
)
updates = {name: str(payload.get(name, "")).strip() for name in names}
if not updates["ARTHUR_BOT_TOKEN"]:
    raise SystemExit("ARTHUR_BOT_TOKEN is missing")
if len(updates["ARTHUR_STORAGE_GATEWAY_API_KEY"]) < 24:
    raise SystemExit("ARTHUR_STORAGE_GATEWAY_API_KEY is invalid")
if not updates["ARTHUR_ALLOWED_USER_IDS"] and not updates["ARTHUR_ALLOWED_USERNAMES"]:
    raise SystemExit("Arthur owner allowlist is missing")
for name, value in updates.items():
    if "\n" in value or "\x00" in value:
        raise SystemExit(f"{name} contains an invalid character")

lines = env_path.read_text(encoding="utf-8-sig").splitlines()
existing: dict[str, str] = {}
for raw in lines:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    existing[key.strip()] = value.strip().strip('"').strip("'")
velvet_token = existing.get("BOT_TOKEN", "").strip()
if velvet_token and hmac.compare_digest(updates["ARTHUR_BOT_TOKEN"], velvet_token):
    raise SystemExit("ARTHUR_BOT_TOKEN must differ from BOT_TOKEN")

result: list[str] = []
seen: set[str] = set()
for raw in lines:
    if "=" in raw:
        name = raw.split("=", 1)[0].strip()
        if name in updates:
            if name not in seen:
                result.append(f"{name}={updates[name]}")
                seen.add(name)
            continue
    result.append(raw)
if result and result[-1].strip():
    result.append("")
for name, value in updates.items():
    if name not in seen:
        result.append(f"{name}={value}")

temporary = env_path.with_name(env_path.name + ".arthur.tmp")
temporary.write_text("\n".join(result).rstrip() + "\n", encoding="utf-8")
os.chmod(temporary, 0o600)
temporary.replace(env_path)
os.chmod(env_path, 0o600)
print("Arthur production credentials installed without printing values.")
PY

VELVET_APP_DIR="$APP_DIR" \
VELVET_DEPLOY_TARGET_SHA="$SOURCE_COMMIT" \
VELVET_DEPLOY_IMAGE="$IMAGE_DIGEST" \
  bash "$APP_DIR/deploy/server/deploy.sh"

# SOURCE_COMMIT owns the verified application image. CHECKOUT_COMMIT differs
# only by this one-time ops workflow and must be restored before reconcile so
# the host bridge sees a clean checkout exactly matching origin/main.
git fetch --prune origin main
test "$(git rev-parse refs/remotes/origin/main)" = "$CHECKOUT_COMMIT"
git merge-base --is-ancestor "$SOURCE_COMMIT" "$CHECKOUT_COMMIT"
git reset --hard "$CHECKOUT_COMMIT"
test "$(git symbolic-ref --short HEAD)" = main
test "$(git rev-parse HEAD)" = "$CHECKOUT_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"

if ! docker exec velvet-hermes-1 test -f /opt/data/tools/reconcilectl.py; then
  sudo -n bash "$APP_DIR/deploy/hermes-reconcile/install.sh"
fi

submit_json="$(docker exec velvet-hermes-1 \
  python /opt/data/tools/reconcilectl.py submit librarian)"
printf '%s\n' "$submit_json"
task_id="$(python3 -c '
import json, sys
payload = json.load(sys.stdin)
if payload.get("ok") is not True or not payload.get("task_id"):
    raise SystemExit("librarian reconcile was not accepted")
print(payload["task_id"])
' <<<"$submit_json")"

wait_json="$(docker exec velvet-hermes-1 \
  python /opt/data/tools/reconcilectl.py wait "$task_id" --interval 5)"
printf '%s\n' "$wait_json"
python3 -c '
import json, sys
payload = json.load(sys.stdin)
if payload.get("ok") is not True or payload.get("status") != "completed":
    raise SystemExit("librarian reconcile did not complete successfully")
' <<<"$wait_json"

compose=(
  docker compose
  --env-file "$APP_DIR/.env.server"
  -f "$APP_DIR/deploy/hermes-librarian/compose.yaml"
  --profile arthur
)

for service in ollama-librarian librarian-hermes arthur-storage-gateway arthur; do
  cid="$("${compose[@]}" ps -q "$service")"
  test -n "$cid"
  state="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$cid")"
  case "$state" in
    healthy|running) ;;
    *) echo "$service is not healthy: $state" >&2; exit 1 ;;
  esac
  ports="$(docker inspect --format '{{json .NetworkSettings.Ports}}' "$cid")"
  python3 -c '
import json, sys
ports = json.loads(sys.stdin.read()) or {}
if any(value for value in ports.values()):
    raise SystemExit("unexpected published port")
' <<<"$ports"
done

"${compose[@]}" exec -T arthur \
  python -c "from pathlib import Path; raise SystemExit(0 if Path('/tmp/arthur-heartbeat').exists() else 1)"
"${compose[@]}" exec -T arthur \
  python -c "import os; raise SystemExit(0 if os.getenv('STORAGE_LIBRARIAN_AUTO_ENQUEUE','').lower() == 'false' else 1)"
"${compose[@]}" exec -T ollama-librarian \
  ollama show velvet-librarian-text:v1 >/dev/null
"${compose[@]}" exec -T arthur python - <<'PY'
import json
import os
import urllib.request

token = os.environ["ARTHUR_BOT_TOKEN"]
with urllib.request.urlopen(
    f"https://api.telegram.org/bot{token}/getMe",
    timeout=10,
) as response:
    payload = json.load(response)
assert payload.get("ok") is True, payload
result = payload.get("result") or {}
assert result.get("is_bot") is True, result
PY

test "$(git rev-parse HEAD)" = "$CHECKOUT_COMMIT"
test "$(git rev-parse refs/remotes/origin/main)" = "$CHECKOUT_COMMIT"
test -z "$(git status --porcelain --untracked-files=all)"
echo "Arthur production rollout verified at app=$SOURCE_COMMIT checkout=$CHECKOUT_COMMIT task=$task_id"
