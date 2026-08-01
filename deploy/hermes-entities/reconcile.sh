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

for path in \
  "$VELVET_ENV_FILE" \
  "$OPERATOR_SOURCE/SOUL.kael.md" \
  "$OPERATOR_SOURCE/AGENTS.kael.md" \
  "$OPERATOR_SOURCE/coderctl.py" \
  "$OPERATOR_SOURCE/runctl.py" \
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

hermes_uid="$(stat -c '%u' "$hermes_data")"
hermes_gid="$(stat -c '%g' "$hermes_data")"

install -d -m 0750 -o "$hermes_uid" -g "$hermes_gid" \
  "$hermes_data/tools" \
  "$hermes_data/orchestration"

install -m 0640 -o "$hermes_uid" -g "$hermes_gid" \
  "$OPERATOR_SOURCE/SOUL.kael.md" \
  "$hermes_data/SOUL.md"
install -m 0640 -o "$hermes_uid" -g "$hermes_gid" \
  "$OPERATOR_SOURCE/AGENTS.kael.md" \
  "$hermes_data/AGENTS.md"
install -m 0500 -o "$hermes_uid" -g "$hermes_gid" \
  "$OPERATOR_SOURCE/coderctl.py" \
  "$hermes_data/tools/coderctl.py"
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

python3 - "$CODERS_ROOT" "$CODERS_SOURCE" <<'PY'
from __future__ import annotations

import os
import sys
from pathlib import Path

root = Path(sys.argv[1])
source = Path(sys.argv[2])

for project in ("velvet", "max"):
    data = root / "data" / project
    workspace = root / "workspaces" / project
    if not data.is_dir():
        raise SystemExit(f"Отсутствует coder data directory: {data}")
    if not (workspace / ".git").is_dir():
        raise SystemExit(f"Отсутствует отдельный coder checkout: {workspace}")

    uid = data.stat().st_uid
    gid = data.stat().st_gid
    soul = source / f"SOUL.{project}.md"
    contract = source / f"AGENTS.{project}.md"

    target_soul = data / "SOUL.md"
    target_soul.write_text(soul.read_text(encoding="utf-8"), encoding="utf-8")
    os.chown(target_soul, uid, gid)
    os.chmod(target_soul, 0o640)

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

print("Kael and coder entity files reconciled.")
PY

printf 'Kael entity: %s/SOUL.md\n' "$hermes_data"
printf 'Kael operations: %s/AGENTS.md\n' "$hermes_data"
printf 'Coder contexts: %s/workspaces/{velvet,max}/.hermes.md\n' "$CODERS_ROOT"
