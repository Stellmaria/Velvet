#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите installer через sudo." >&2
  exit 1
fi

VELVET_APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
VELVET_ENV_FILE="${VELVET_ENV_FILE:-$VELVET_APP_DIR/.env.server}"
HERMES_ENV_FILE="${HERMES_ENV_FILE:-$VELVET_APP_DIR/.env.hermes}"
VELVET_COMPOSE_FILE="${VELVET_COMPOSE_FILE:-$VELVET_APP_DIR/docker-compose.server.yml}"
SERVICE_USER="${HERMES_ORCHESTRATION_SERVICE_USER:-velvet}"
SOURCE_DIR="$VELVET_APP_DIR/deploy/hermes-librarian"
BRAIN_SOURCE="$VELVET_APP_DIR/deploy/hermes-brain"
UNIT_SOURCE="$VELVET_APP_DIR/deploy/systemd/velvet-librarian.service"
UNIT_TARGET="/etc/systemd/system/velvet-librarian.service"

for path in \
  "$VELVET_ENV_FILE" \
  "$HERMES_ENV_FILE" \
  "$VELVET_COMPOSE_FILE" \
  "$SOURCE_DIR/compose.yaml" \
  "$SOURCE_DIR/prepare_profile.py" \
  "$SOURCE_DIR/Modelfile.text" \
  "$SOURCE_DIR/Modelfile.vision" \
  "$SOURCE_DIR/start.sh" \
  "$SOURCE_DIR/SOUL.md" \
  "$SOURCE_DIR/AGENTS.md" \
  "$BRAIN_SOURCE/context_compiler.py" \
  "$VELVET_APP_DIR/brain-vault/manifest.json" \
  "$UNIT_SOURCE"
do
  if [[ ! -f "$path" ]]; then
    echo "Отсутствует обязательный файл: $path" >&2
    exit 2
  fi
done

pack_root="$(mktemp -d)"
trap 'rm -rf -- "$pack_root"' EXIT
python3 "$BRAIN_SOURCE/context_compiler.py" validate
python3 "$BRAIN_SOURCE/context_compiler.py" compile \
  --entity velvet-librarian \
  --output "$pack_root/velvet-librarian"

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  echo "Не найден service user: $SERVICE_USER" >&2
  exit 2
fi

python3 - "$VELVET_ENV_FILE" <<'PY'
from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

path = Path(sys.argv[1])
lines = path.read_text(encoding="utf-8-sig").splitlines()
values = {}
for raw in lines:
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

key = values.get("STORAGE_LIBRARIAN_HERMES_API_KEY", "")
if len(key) < 24:
    key = secrets.token_urlsafe(48)

updates = {
    "STORAGE_LIBRARIAN_HERMES_BASE_URL": "http://librarian-hermes:8642",
    "STORAGE_LIBRARIAN_HERMES_API_KEY": key,
    "STORAGE_LIBRARIAN_ANALYZER_VERSION": "velvet-librarian:qwen3-4b-text:v4",
    "STORAGE_LIBRARIAN_PUBLISH_REPORTS": "true",
    "STORAGE_LIBRARIAN_OLLAMA_BASE_URL": "http://ollama-librarian:11434",
    "STORAGE_LIBRARIAN_TEXT_MODEL": "velvet-librarian-text:v1",
    "STORAGE_LIBRARIAN_VISION_MODEL": "velvet-librarian-vision:v1",
    "STORAGE_LIBRARIAN_TEXT_CONTEXT_LENGTH": "8192",
    "STORAGE_LIBRARIAN_TEXT_MAX_OUTPUT_TOKENS": "384",
    "STORAGE_LIBRARIAN_VISION_CONTEXT_LENGTH": "16384",
    "STORAGE_LIBRARIAN_VISION_MAX_OUTPUT_TOKENS": "640",
    "STORAGE_LIBRARIAN_OLLAMA_KEEP_ALIVE": "5m",
    "STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS": "180",
}
result = []
seen = set()
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
path.write_text("\n".join(result).rstrip() + "\n", encoding="utf-8")
os.chmod(path, 0o600)
print("Velvet Librarian credentials and local inference settings prepared without printing secret values.")
PY

readarray -t resolved < <(python3 - "$VELVET_ENV_FILE" <<'PY'
from pathlib import Path
import sys

values = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")
print(values.get("VELVET_DATA_DIR", "/srv/velvet/data"))
print(values.get("HERMES_IMAGE", "nousresearch/hermes-agent@sha256:f7b35053268f532f98955195c909f15a230470fbcbdacaa9fdecb95707dad04a"))
print(values.get("STORAGE_LIBRARIAN_TEXT_MODEL", "velvet-librarian-text:v1"))
print(values.get("STORAGE_LIBRARIAN_VISION_MODEL", "velvet-librarian-vision:v1"))
print(values.get("STORAGE_LIBRARIAN_OLLAMA_BASE_URL", "http://ollama-librarian:11434") + "/v1")
print(values.get("STORAGE_LIBRARIAN_TEXT_CONTEXT_LENGTH", "8192"))
PY
)
VELVET_DATA_DIR="${resolved[0]}"
HERMES_IMAGE="${resolved[1]}"
TEXT_MODEL="${resolved[2]}"
VISION_MODEL="${resolved[3]}"
LOCAL_BASE_URL="${resolved[4]}"
LOCAL_CONTEXT_LENGTH="${resolved[5]}"
SOURCE_CONFIG="$VELVET_DATA_DIR/hermes/config.yaml"
TARGET_DIR="$VELVET_DATA_DIR/hermes-librarian"
ARTHUR_TARGET_DIR="$VELVET_DATA_DIR/arthur"

if [[ ! -f "$SOURCE_CONFIG" ]]; then
  echo "Отсутствует config основного Hermes: $SOURCE_CONFIG" >&2
  exit 3
fi

source_uid="$(stat -c '%u' "$VELVET_DATA_DIR/hermes")"
source_gid="$(stat -c '%g' "$VELVET_DATA_DIR/hermes")"
install -d -m 0750 -o "$source_uid" -g "$source_gid" "$TARGET_DIR"
install -d -m 0750 -o 10001 -g 10001 "$ARTHUR_TARGET_DIR"

docker run --rm \
  --network none \
  --entrypoint python \
  -e STORAGE_LIBRARIAN_TEXT_MODEL="$TEXT_MODEL" \
  -e STORAGE_LIBRARIAN_OLLAMA_BASE_URL="${LOCAL_BASE_URL%/v1}" \
  -e STORAGE_LIBRARIAN_TEXT_CONTEXT_LENGTH="$LOCAL_CONTEXT_LENGTH" \
  -v "$SOURCE_CONFIG:/source/config.yaml:ro" \
  -v "$SOURCE_DIR:/bootstrap:ro" \
  -v "$pack_root/velvet-librarian:/brain:ro" \
  -v "$TARGET_DIR:/target" \
  "$HERMES_IMAGE" \
  /bootstrap/prepare_profile.py \
  /source/config.yaml \
  /target \
  /brain/SOUL.md \
  /brain/AGENTS.md \
  /brain/context-manifest.json

chown -R "$source_uid:$source_gid" "$TARGET_DIR"
find "$TARGET_DIR" -type d -exec chmod 0750 {} +
find "$TARGET_DIR" -type f -exec chmod 0640 {} +

docker run --rm -i \
  --network none \
  --entrypoint python \
  -e STORAGE_LIBRARIAN_TEXT_MODEL="$TEXT_MODEL" \
  -e STORAGE_LIBRARIAN_OLLAMA_BASE_URL="${LOCAL_BASE_URL%/v1}" \
  -e STORAGE_LIBRARIAN_TEXT_CONTEXT_LENGTH="$LOCAL_CONTEXT_LENGTH" \
  -v "$TARGET_DIR:/profile:ro" \
  "$HERMES_IMAGE" \
  - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import yaml

config = yaml.safe_load(Path("/profile/config.yaml").read_text(encoding="utf-8")) or {}
platform = config.get("platform_toolsets") or {}
agent = config.get("agent") or {}
disabled = set(agent.get("disabled_toolsets") or [])
model = config.get("model") or {}
required = {"terminal", "file", "web", "browser", "messaging", "memory", "delegation", "code_execution", "skills"}
assert platform.get("api_server") == [], platform
assert required.issubset(disabled), sorted(required - disabled)
assert config.get("mcp_servers") == {}, config.get("mcp_servers")
assert config.get("fallback_providers") == [], config.get("fallback_providers")
assert model.get("provider") == "custom", model
assert model.get("default") == os.environ["STORAGE_LIBRARIAN_TEXT_MODEL"], model
expected_base_url = os.environ["STORAGE_LIBRARIAN_OLLAMA_BASE_URL"].rstrip("/") + "/v1"
assert model.get("base_url") == expected_base_url, model
assert int(model.get("context_length") or 0) == int(os.environ["STORAGE_LIBRARIAN_TEXT_CONTEXT_LENGTH"]), model
assert (config.get("compression") or {}).get("enabled") is True, config.get("compression")
guardrails = config.get("tool_loop_guardrails") or {}
assert guardrails.get("warnings_enabled") is True, guardrails
assert guardrails.get("hard_stop_enabled") is True, guardrails
root = Path("/profile")
manifest = json.loads((root / "context-manifest.json").read_text(encoding="utf-8"))
assert manifest.get("entity_id") == "velvet-librarian", manifest
outputs = {item["path"]: item for item in manifest.get("outputs", [])}
for name in ("SOUL.md", "AGENTS.md"):
    digest = hashlib.sha256((root / name).read_bytes()).hexdigest()
    assert digest == outputs[name]["sha256"], name
print("Velvet Librarian local-only deny-all contract: OK")
PY

install -m 0644 "$UNIT_SOURCE" "$UNIT_TARGET"
systemctl daemon-reload
systemctl enable velvet-librarian.service
systemctl restart velvet-librarian.service

runuser -u "$SERVICE_USER" -- bash -ceu "
  cd '$VELVET_APP_DIR'
  docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
    up -d --force-recreate bot
"

healthy=false
for _ in $(seq 1 45); do
  if runuser -u "$SERVICE_USER" -- bash -ceu "
    cd '$VELVET_APP_DIR'
    docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
      exec -T bot python - <<'PY'
import json
import os
import urllib.request

request = urllib.request.Request(
    os.environ['STORAGE_LIBRARIAN_HERMES_BASE_URL'].rstrip('/') + '/health',
    headers={'Authorization': 'Bearer ' + os.environ['STORAGE_LIBRARIAN_HERMES_API_KEY']},
)
with urllib.request.urlopen(request, timeout=3) as response:
    payload = json.load(response)
raise SystemExit(0 if payload.get('status') == 'ok' else 1)
PY
  " >/dev/null 2>&1; then
    healthy=true
    break
  fi
  sleep 2
done

if [[ "$healthy" != "true" ]]; then
  systemctl --no-pager --full status velvet-librarian.service >&2 || true
  runuser -u "$SERVICE_USER" -- \
    docker compose --env-file "$VELVET_ENV_FILE" -f "$SOURCE_DIR/compose.yaml" \
      logs --tail=120 ollama-librarian librarian-hermes >&2 || true
  echo "Velvet Librarian API не достиг healthy status." >&2
  exit 4
fi

runuser -u "$SERVICE_USER" -- \
  docker compose --env-file "$VELVET_ENV_FILE" -f "$SOURCE_DIR/compose.yaml" \
    exec -T ollama-librarian ollama show "$TEXT_MODEL" >/dev/null
runuser -u "$SERVICE_USER" -- \
  docker compose --env-file "$VELVET_ENV_FILE" -f "$SOURCE_DIR/compose.yaml" \
    exec -T ollama-librarian ollama show "$VISION_MODEL" >/dev/null

ollama_smoke=false
for _ in $(seq 1 3); do
  if runuser -u "$SERVICE_USER" -- bash -ceu "
    cd '$VELVET_APP_DIR'
    docker compose --env-file '$VELVET_ENV_FILE' -f '$VELVET_COMPOSE_FILE' \
      exec -T bot python - <<'PY'
import json
import os
import urllib.request

schema = {
    'type': 'object',
    'additionalProperties': False,
    'required': ['status'],
    'properties': {'status': {'type': 'string', 'enum': ['ok']}},
}
payload = {
    'model': os.environ['STORAGE_LIBRARIAN_TEXT_MODEL'],
    'stream': False,
    'think': False,
    'keep_alive': 0,
    'format': schema,
    'messages': [{'role': 'user', 'content': 'Верни только JSON со значением status=ok.'}],
    'options': {'num_ctx': 2048, 'num_predict': 16, 'temperature': 0},
}
request = urllib.request.Request(
    os.environ['STORAGE_LIBRARIAN_OLLAMA_BASE_URL'].rstrip('/') + '/api/chat',
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST',
)
timeout = max(30, min(int(os.environ.get('STORAGE_LIBRARIAN_RUN_TIMEOUT_SECONDS', '180')), 300))
with urllib.request.urlopen(request, timeout=timeout) as response:
    result = json.load(response)
assert result.get('done') is True, result.get('done')
assert result.get('done_reason') == 'stop', result.get('done_reason')
message = result.get('message')
assert isinstance(message, dict), type(message).__name__
content = message.get('content')
assert isinstance(content, str) and content.strip(), 'missing content'
decoded = json.loads(content)
assert decoded == {'status': 'ok'}, decoded
PY
  " >/dev/null 2>&1; then
    ollama_smoke=true
    break
  fi
  sleep 5
done

if [[ "$ollama_smoke" != "true" ]]; then
  systemctl --no-pager --full status velvet-librarian.service >&2 || true
  runuser -u "$SERVICE_USER" -- \
    docker compose --env-file "$VELVET_ENV_FILE" -f "$SOURCE_DIR/compose.yaml" \
      logs --tail=160 ollama-librarian librarian-hermes >&2 || true
  echo "Bot-to-Ollama structured analysis smoke не прошёл." >&2
  exit 5
fi

printf '%s\n' \
  "Velvet Librarian profile installed." \
  "Dedicated API key configured." \
  "Text model configured: $TEXT_MODEL." \
  "Vision alias prepared; image support remains incomplete until image bytes are supplied." \
  "Analyzer version set to velvet-librarian:qwen3-4b-text:v4." \
  "Hermes Reports publication enabled." \
  "Bot-to-Hermes health verified." \
  "Bot-to-Ollama structured analysis smoke verified." \
  "Automatic enqueue remains controlled by STORAGE_LIBRARIAN_AUTO_ENQUEUE."
