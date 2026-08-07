#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Запустите reconcile через sudo." >&2
  exit 1
fi

VELVET_APP_DIR="${VELVET_APP_DIR:-/srv/velvet}"
VELVET_ENV_FILE="${VELVET_ENV_FILE:-$VELVET_APP_DIR/.env.server}"
CODERS_ROOT="${HERMES_CODERS_ROOT:-/srv/hermes-coders}"
OPERATOR_SOURCE="$VELVET_APP_DIR/deploy/hermes-operator"
CODERS_SOURCE="$VELVET_APP_DIR/deploy/hermes-coders"
BRAIN_SOURCE="$VELVET_APP_DIR/deploy/hermes-brain"
KAEL_CODER_PLUGIN_SOURCE="$OPERATOR_SOURCE/plugins/kael-coder-control"

for path in \
  "$VELVET_ENV_FILE" \
  "$BRAIN_SOURCE/context_compiler.py" \
  "$BRAIN_SOURCE/install_context_pack.py" \
  "$BRAIN_SOURCE/verify_installed_context.py" \
  "$VELVET_APP_DIR/brain-vault/manifest.json" \
  "$CODERS_SOURCE/ensure_runtime_config.py" \
  "$OPERATOR_SOURCE/coderctl.py" \
  "$OPERATOR_SOURCE/review_gate.py" \
  "$OPERATOR_SOURCE/runctl.py" \
  "$KAEL_CODER_PLUGIN_SOURCE/plugin.yaml" \
  "$KAEL_CODER_PLUGIN_SOURCE/__init__.py" \
  "$CODERS_SOURCE/SOUL.velvet.md" \
  "$CODERS_SOURCE/SOUL.max.md" \
  "$CODERS_SOURCE/AGENTS.velvet.md" \
  "$CODERS_SOURCE/AGENTS.max.md"
do
  if [[ ! -f "$path" ]]; then
    echo "Отсутствует обязательный файл: $path" >&2
    exit 2
  fi
done

velvet_data_dir="$(python3 - "$VELVET_ENV_FILE" <<'PY'
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
PY
)"

hermes_data="$velvet_data_dir/hermes"
if [[ ! -d "$hermes_data" ]]; then
  echo "Отсутствует data directory основного Hermes: $hermes_data" >&2
  exit 3
fi
if [[ ! -f "$hermes_data/config.yaml" ]]; then
  echo "Отсутствует config основного Hermes: $hermes_data/config.yaml" >&2
  exit 3
fi

pack_root="$(mktemp -d)"
trap 'rm -rf -- "$pack_root"' EXIT
python3 "$BRAIN_SOURCE/context_compiler.py" validate
for entity in kael velvet-coder max-coder; do
  python3 "$BRAIN_SOURCE/context_compiler.py" compile \
    --entity "$entity" \
    --output "$pack_root/$entity"
done

hermes_uid="$(stat -c '%u' "$hermes_data")"
hermes_gid="$(stat -c '%g' "$hermes_data")"
kael_plugin_target="$hermes_data/plugins/kael-coder-control"

install -d -m 0750 -o "$hermes_uid" -g "$hermes_gid" \
  "$hermes_data/tools" \
  "$hermes_data/orchestration" \
  "$hermes_data/plugins" \
  "$kael_plugin_target"
install -d -m 0700 -o "$hermes_uid" -g "$hermes_gid" \
  "$hermes_data/audit"
install -m 0640 -o "$hermes_uid" -g "$hermes_gid" \
  "$KAEL_CODER_PLUGIN_SOURCE/plugin.yaml" \
  "$kael_plugin_target/plugin.yaml"
install -m 0640 -o "$hermes_uid" -g "$hermes_gid" \
  "$KAEL_CODER_PLUGIN_SOURCE/__init__.py" \
  "$kael_plugin_target/__init__.py"

python3 "$BRAIN_SOURCE/install_context_pack.py" \
  --pack "$pack_root/kael" \
  --target "$hermes_data" \
  --entity kael \
  --mode hermes
python3 "$CODERS_SOURCE/ensure_runtime_config.py" \
  --profile kael \
  "$hermes_data/config.yaml"
install -m 0500 -o "$hermes_uid" -g "$hermes_gid" \
  "$OPERATOR_SOURCE/coderctl.py" \
  "$hermes_data/tools/coderctl.py"
install -m 0500 -o "$hermes_uid" -g "$hermes_gid" \
  "$OPERATOR_SOURCE/review_gate.py" \
  "$hermes_data/tools/review_gate.py"
install -m 0500 -o "$hermes_uid" -g "$hermes_gid" \
  "$OPERATOR_SOURCE/runctl.py" \
  "$hermes_data/tools/runctl.py"

if [[ -f "$hermes_data/tools/opsctl.py" ]]; then
  chown "$hermes_uid:$hermes_gid" "$hermes_data/tools/opsctl.py"
  chmod 0500 "$hermes_data/tools/opsctl.py"
fi

ledger="$hermes_data/orchestration/tasks.json"
lock="$ledger.lock"
if [[ ! -f "$ledger" ]]; then
  printf '[]\n' >"$ledger"
fi
if [[ ! -f "$lock" ]]; then
  : >"$lock"
fi
chown "$hermes_uid:$hermes_gid" "$ledger" "$lock"
chmod 0600 "$ledger" "$lock"

for project in velvet max; do
  entity="$project-coder"
  python3 "$BRAIN_SOURCE/install_context_pack.py" \
    --pack "$pack_root/$entity" \
    --target "$CODERS_ROOT/data/$project" \
    --entity "$entity" \
    --mode hermes
  if [[ -d "$CODERS_ROOT/codex/$project" ]]; then
    python3 "$BRAIN_SOURCE/install_context_pack.py" \
      --pack "$pack_root/$entity" \
      --target "$CODERS_ROOT/codex/$project" \
      --entity "$entity" \
      --mode codex
    python3 "$BRAIN_SOURCE/verify_installed_context.py" \
      --target "$CODERS_ROOT/codex/$project" \
      --entity "$entity" \
      --mode codex
  fi
  python3 "$BRAIN_SOURCE/verify_installed_context.py" \
    --target "$CODERS_ROOT/data/$project" \
    --entity "$entity" \
    --mode hermes
done

python3 "$BRAIN_SOURCE/verify_installed_context.py" \
  --target "$hermes_data" \
  --entity kael \
  --mode hermes

python3 - "$CODERS_ROOT" "$pack_root" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
packs = Path(sys.argv[2])

for project in ("velvet", "max"):
    data = root / "data" / project
    workspace = root / "workspaces" / project
    if not data.is_dir():
        raise SystemExit(f"Отсутствует coder data directory: {data}")
    if not (workspace / ".git").is_dir():
        raise SystemExit(f"Отсутствует отдельный coder checkout: {workspace}")

    entity = f"{project}-coder"
    contract = packs / entity / "AGENTS.md"

    sections: list[str] = []
    repository_agents = workspace / "AGENTS.md"
    if repository_agents.is_file():
        sections.append(repository_agents.read_text(encoding="utf-8").strip())
    sections.append(contract.read_text(encoding="utf-8").strip())

    generated = workspace / ".hermes.md"
    generated.write_text(
        "\n\n---\n\n".join(section for section in sections if section).rstrip()
        + "\n",
        encoding="utf-8",
    )
    workspace_uid = workspace.stat().st_uid
    workspace_gid = workspace.stat().st_gid
    os.chown(generated, workspace_uid, workspace_gid)
    os.chmod(generated, 0o640)

    exclude = workspace / ".git" / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    lines = exclude.read_text(encoding="utf-8").splitlines() if exclude.exists() else []
    if ".hermes.md" not in {line.strip() for line in lines}:
        lines.append(".hermes.md")
        exclude.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    os.chown(exclude, workspace_uid, workspace_gid)

print("Kael and isolated coder Brain context packs reconciled.")
PY

printf 'Kael entity: %s/SOUL.md\n' "$hermes_data"
printf 'Kael operations: %s/AGENTS.md\n' "$hermes_data"
printf 'Kael coder control: %s and plugins.enabled\n' "$kael_plugin_target"
printf 'Coder contexts: %s/workspaces/{velvet,max}/.hermes.md\n' "$CODERS_ROOT"
printf 'Brain manifests: %s/context-manifest.json and %s/{data,codex}/{velvet,max}/context-manifest.json\n' \
  "$hermes_data" "$CODERS_ROOT"
