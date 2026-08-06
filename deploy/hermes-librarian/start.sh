#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
ENV_FILE="${VELVET_ENV_FILE:-$APP_DIR/.env.server}"
COMPOSE_FILE="${LIBRARIAN_COMPOSE_FILE:-$APP_DIR/deploy/hermes-librarian/compose.yaml}"
readarray -t runtime_values < <(python3 - "$ENV_FILE" <<'PY'
from __future__ import annotations

import hmac
import os
import sys
from pathlib import Path

values: dict[str, str] = {}
for raw in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    values[key.strip()] = value.strip().strip('"').strip("'")

print(os.getenv("STORAGE_LIBRARIAN_TEXT_MODEL") or values.get(
    "STORAGE_LIBRARIAN_TEXT_MODEL", "velvet-librarian-text:v1"
))
print(os.getenv("STORAGE_LIBRARIAN_VISION_MODEL") or values.get(
    "STORAGE_LIBRARIAN_VISION_MODEL", "velvet-librarian-vision:v1"
))
arthur_token = values.get("ARTHUR_BOT_TOKEN", "").strip()
velvet_token = values.get("BOT_TOKEN", "").strip()
if arthur_token and velvet_token and hmac.compare_digest(arthur_token, velvet_token):
    raise SystemExit("ARTHUR_BOT_TOKEN must not reuse BOT_TOKEN.")
arthur_ready = bool(arthur_token) and bool(
    values.get("ARTHUR_STORAGE_GATEWAY_API_KEY", "").strip()
) and bool(
    values.get("ARTHUR_ALLOWED_USER_IDS", "").strip()
    or values.get("ARTHUR_ALLOWED_USERNAMES", "").strip()
)
print("true" if arthur_ready else "false")
PY
)
TEXT_MODEL="${runtime_values[0]}"
VISION_MODEL="${runtime_values[1]}"
ARTHUR_READY="${runtime_values[2]}"
TEXT_SOURCE_MODEL="qwen3:4b-instruct"
VISION_SOURCE_MODEL="qwen3.5:9b-q4_K_M"

compose=(docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

"${compose[@]}" up -d ollama-librarian

ready=false
for _ in $(seq 1 90); do
  if "${compose[@]}" exec -T ollama-librarian ollama list >/dev/null 2>&1; then
    ready=true
    break
  fi
  sleep 2
done

if [[ "$ready" != "true" ]]; then
  "${compose[@]}" logs --tail=120 ollama-librarian >&2 || true
  echo "Локальный Ollama Librarian не достиг healthy state." >&2
  exit 1
fi

if ! "${compose[@]}" exec -T ollama-librarian \
  ollama show "$TEXT_SOURCE_MODEL" >/dev/null 2>&1; then
  "${compose[@]}" exec -T ollama-librarian ollama pull "$TEXT_SOURCE_MODEL"
fi
if ! "${compose[@]}" exec -T ollama-librarian \
  ollama show "$VISION_SOURCE_MODEL" >/dev/null 2>&1; then
  "${compose[@]}" exec -T ollama-librarian ollama pull "$VISION_SOURCE_MODEL"
fi

"${compose[@]}" exec -T ollama-librarian \
  ollama create "$TEXT_MODEL" -f /bootstrap/Modelfile.text
"${compose[@]}" exec -T ollama-librarian \
  ollama create "$VISION_MODEL" -f /bootstrap/Modelfile.vision
"${compose[@]}" exec -T ollama-librarian ollama show "$TEXT_MODEL" >/dev/null
"${compose[@]}" exec -T ollama-librarian ollama show "$VISION_MODEL" >/dev/null

"${compose[@]}" up -d --force-recreate librarian-hermes

if [[ "$ARTHUR_READY" == "true" ]]; then
  "${compose[@]}" --profile arthur up -d --no-deps --force-recreate \
    arthur-storage-gateway

  gateway_healthy=false
  for _ in $(seq 1 60); do
    if "${compose[@]}" --profile arthur exec -T arthur-storage-gateway \
      python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8786/health', timeout=3).read()" \
      >/dev/null 2>&1; then
      gateway_healthy=true
      break
    fi
    sleep 2
  done
  if [[ "$gateway_healthy" != "true" ]]; then
    "${compose[@]}" --profile arthur logs --tail=160 \
      arthur-storage-gateway >&2 || true
    echo "Arthur Storage gateway не достиг healthy state." >&2
    exit 2
  fi

  "${compose[@]}" --profile arthur up -d --no-deps --force-recreate arthur

  arthur_healthy=false
  for _ in $(seq 1 60); do
    if "${compose[@]}" --profile arthur exec -T arthur \
      python -c "from pathlib import Path; raise SystemExit(0 if Path('/tmp/arthur-heartbeat').exists() else 1)" \
      >/dev/null 2>&1; then
      arthur_healthy=true
      break
    fi
    sleep 2
  done
  if [[ "$arthur_healthy" != "true" ]]; then
    "${compose[@]}" --profile arthur logs --tail=160 \
      arthur-storage-gateway arthur >&2 || true
    echo "Arthur runtime не достиг healthy state." >&2
    exit 3
  fi

  "${compose[@]}" --profile arthur exec -T arthur python - <<'PY'
import asyncio
import json

import aiohttp

from velvet_bot.core.config.arthur import ArthurSettings
from velvet_bot.domains.telegram_storage.librarian_models import (
    StorageLibrarianSettings,
)
from velvet_bot.infrastructure.ai.storage_librarian_ollama import (
    OllamaStorageAnalysisClient,
)


async def main() -> None:
    arthur = ArthurSettings.from_env()
    gateway_url = (
        arthur.storage_gateway_base_url
        + "/v1/storage/9223372036854775807"
    )
    async with aiohttp.ClientSession(
        headers={"Authorization": f"Bearer {arthur.storage_gateway_api_key}"},
    ) as session:
        async with session.get(
            gateway_url,
            params={"max_bytes": "1"},
        ) as response:
            assert response.status == 404, await response.text()

    settings = StorageLibrarianSettings.from_env()
    result = await OllamaStorageAnalysisClient(settings).run(
        prompt="Источник: health=ok. Верни краткий анализ.",
        session_id="arthur-install-smoke",
        instructions=(
            "Верни JSON по обязательной schema. summary на русском; "
            "confidence отражает уверенность по источнику."
        ),
    )
    decoded = json.loads(result.output)
    assert result.analyzer == "ollama", result.analyzer
    assert decoded["summary"], decoded
    assert 0 <= decoded["confidence"] <= 100, decoded


asyncio.run(main())
PY
else
  printf '%s\n' \
    "Arthur profile не запущен: задайте отдельный ARTHUR_BOT_TOKEN, gateway key и owner allowlist."
fi
