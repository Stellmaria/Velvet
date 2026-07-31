#!/bin/sh
set -eu

model="${VISION_MODEL:?VISION_MODEL must be configured}"
expected_digest="${VISION_MODEL_EXPECTED_DIGEST:-}"
startup_timeout="${VISION_RUNTIME_STARTUP_TIMEOUT_SECONDS:-60}"

export OLLAMA_MODELS="${OLLAMA_MODELS:-/root/.ollama/models}"
export OLLAMA_KEEP_ALIVE="0"
export OLLAMA_NUM_PARALLEL="1"
export OLLAMA_MAX_LOADED_MODELS="1"

OLLAMA_HOST=0.0.0.0:11434 ollama serve &
runtime_pid=$!

shutdown() {
  kill -TERM "$runtime_pid" 2>/dev/null || true
  wait "$runtime_pid" 2>/dev/null || true
}
trap shutdown INT TERM EXIT

export OLLAMA_HOST=http://127.0.0.1:11434
elapsed=0
until ollama list >/dev/null 2>&1; do
  if [ "$elapsed" -ge "$startup_timeout" ]; then
    echo "Vision model loader runtime did not start within ${startup_timeout}s." >&2
    exit 1
  fi
  sleep 1
  elapsed=$((elapsed + 1))
done

installed_id="$(ollama list | awk -v target="$model" 'NR > 1 && $1 == target {print $2; exit}')"
if [ -n "$installed_id" ]; then
  actual_lower="$(printf '%s' "$installed_id" | tr '[:upper:]' '[:lower:]')"
  expected_lower="$(printf '%s' "$expected_digest" | tr '[:upper:]' '[:lower:]')"
  if [ -z "$expected_digest" ]; then
    echo "Vision model already installed model=$model digest=$installed_id"
    exit 0
  fi
  case "$actual_lower" in
    "$expected_lower"*)
      echo "Vision model already installed model=$model digest=$installed_id"
      exit 0
      ;;
  esac
fi

echo "Pulling configured vision model: $model"
ollama pull "$model"
installed_id="$(ollama list | awk -v target="$model" 'NR > 1 && $1 == target {print $2; exit}')"

if [ -z "$installed_id" ]; then
  echo "Vision model is missing after pull: $model" >&2
  exit 1
fi

if [ -n "$expected_digest" ]; then
  actual_lower="$(printf '%s' "$installed_id" | tr '[:upper:]' '[:lower:]')"
  expected_lower="$(printf '%s' "$expected_digest" | tr '[:upper:]' '[:lower:]')"
  case "$actual_lower" in
    "$expected_lower"*) ;;
    *)
      echo "Vision model digest mismatch: expected prefix $expected_digest, got $installed_id" >&2
      exit 1
      ;;
  esac
fi

echo "Vision model installed model=$model digest=$installed_id"
