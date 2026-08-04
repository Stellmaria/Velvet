from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


ROOT = Path(os.environ.get("HERMES_CODERS_ROOT", "/srv/hermes-coders"))
SOURCE_DIR = Path(__file__).resolve().parent
COMPOSE_FILES = (
    SOURCE_DIR / "compose.yaml",
    SOURCE_DIR / "compose.runtime.yaml",
    SOURCE_DIR / "compose.security.yaml",
)
STARTUP_TIMEOUT_SECONDS = max(
    30,
    int(os.environ.get("HERMES_CODERS_SMOKE_TIMEOUT_SECONDS", "180")),
)
POLL_INTERVAL_SECONDS = max(
    1.0,
    float(os.environ.get("HERMES_CODERS_SMOKE_POLL_SECONDS", "3")),
)
CODEX_VERSION = "0.144.1"
CODEX_MODELS = ("gpt-5.6-luna", "gpt-5.6-terra", "gpt-5.6-sol")
CRYPTOGRAPHY_VERSION = "50.0.0"


@dataclass(frozen=True)
class CoderTarget:
    project: str
    coder_service: str
    chat_service: str
    repository: str


CODERS = (
    CoderTarget(
        project="velvet",
        coder_service="hermes-coder-velvet",
        chat_service="hermes-chat-velvet",
        repository="Stellmaria/Velvet",
    ),
    CoderTarget(
        project="max",
        coder_service="hermes-coder-max",
        chat_service="hermes-chat-max",
        repository="Stellmaria/romatic_club_bot_max",
    ),
)


class SmokeError(RuntimeError):
    pass


Runner = Callable[[Sequence[str], int], subprocess.CompletedProcess[str]]

_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[opsu]_[A-Za-z0-9]+"),
    re.compile(r"(?i)(token\s*[=:]\s*)\S+"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)\S+"),
)


def redact(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        replacement = r"\1[REDACTED]" if pattern.groups else "[REDACTED]"
        result = pattern.sub(replacement, result)
    return result


def _default_runner(
    args: Sequence[str], timeout_seconds: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )


def compose_prefix() -> list[str]:
    return [
        "docker",
        "compose",
        "--profile",
        "velvet",
        "--profile",
        "max",
        *[part for path in COMPOSE_FILES for part in ("-f", str(path))],
    ]


def _result_details(result: subprocess.CompletedProcess[str]) -> str:
    details = "\n".join(
        part.strip()
        for part in (result.stderr or "", result.stdout or "")
        if part.strip()
    )
    return redact(details[:2000]) or "без диагностического вывода"


def run_checked(
    args: Sequence[str],
    *,
    timeout_seconds: int,
    runner: Runner = _default_runner,
) -> subprocess.CompletedProcess[str]:
    try:
        result = runner(args, timeout_seconds)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SmokeError(
            f"Не удалось выполнить {' '.join(args[:4])}: {type(exc).__name__}"
        ) from exc
    if result.returncode != 0:
        raise SmokeError(
            f"Команда завершилась с кодом {result.returncode}: "
            f"{_result_details(result)}"
        )
    return result


def gateway_probe_command(service: str) -> list[str]:
    return [
        *compose_prefix(),
        "exec",
        "-T",
        service,
        "python",
        "-c",
        (
            "import urllib.request; "
            "urllib.request.urlopen('http://127.0.0.1:8642/health', timeout=3).read()"
        ),
    ]


def wait_for_service(
    service: str,
    *,
    timeout_seconds: int = STARTUP_TIMEOUT_SECONDS,
    poll_seconds: float = POLL_INTERVAL_SECONDS,
    runner: Runner = _default_runner,
    monotonic: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    deadline = monotonic() + timeout_seconds
    last_details = "контейнер ещё не ответил"
    while monotonic() < deadline:
        try:
            result = runner(gateway_probe_command(service), 10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_details = type(exc).__name__
        else:
            if result.returncode == 0:
                return
            last_details = _result_details(result)
        sleeper(poll_seconds)
    raise SmokeError(
        f"Service {service} не стал готов за {timeout_seconds} секунд: {last_details}"
    )


def github_probe_script(target: CoderTarget) -> str:
    repository = target.repository
    https_remote = f"https://github.com/{repository}"
    return f"""set -eu

test -n "${{GH_TOKEN:-}}"
test -r /opt/data/config.yaml
test -r /opt/data/context-manifest.json
python - <<'PYCONFIG'
import hashlib
import json
from pathlib import Path

text = Path('/opt/data/config.yaml').read_text(encoding='utf-8')
if 'env_passthrough:' not in text or '- GH_TOKEN' not in text:
    raise SystemExit('runtime config does not pass GH_TOKEN to terminal')
manifest = json.loads(Path('/opt/data/context-manifest.json').read_text(encoding='utf-8'))
if manifest.get('entity_id') != '{target.project}-coder':
    raise SystemExit('unexpected Hermes entity context')
outputs = {{item['path']: item for item in manifest.get('outputs', [])}}
for name in ('SOUL.md', 'AGENTS.md'):
    path = Path('/opt/data') / name
    record = outputs.get(name) or {{}}
    if hashlib.sha256(path.read_bytes()).hexdigest() != record.get('sha256'):
        raise SystemExit('Hermes context hash mismatch: ' + name)
PYCONFIG

gh api user --jq .login >/dev/null
actual_repo="$(gh api repos/{repository} --jq .full_name)"
test "$actual_repo" = "{repository}"
push_allowed="$(gh api repos/{repository} --jq '.permissions.push')"
test "$push_allowed" = "true"

remote="$(git -C /workspace remote get-url origin)"
case "$remote" in
  {https_remote}|{https_remote}.git) ;;
  *) echo "unexpected origin remote for {target.project}" >&2; exit 31 ;;
esac

helper="$(git config --global --get credential.https://github.com.helper || true)"
case "$helper" in
  *"gh auth git-credential"*) ;;
  *) echo "GitHub credential helper is not configured for {target.project}" >&2; exit 32 ;;
esac

git -C /workspace push --dry-run origin \
  HEAD:refs/heads/hermes-auth-smoke-{target.project} >/dev/null
"""


def github_probe_command(target: CoderTarget) -> list[str]:
    return [
        *compose_prefix(),
        "exec",
        "-T",
        target.chat_service,
        "sh",
        "-ceu",
        github_probe_script(target),
    ]


def codex_probe_script(target: CoderTarget) -> str:
    repository = target.repository
    https_remote = f"https://github.com/{repository}"
    models_json = json.dumps(CODEX_MODELS)
    return f"""set -eu

test -s /opt/codex/auth.json
test "$HOME" = "/opt/codex"
test -r /opt/codex/AGENTS.md
test -r /opt/codex/output.schema.json
test -r /opt/codex/context-manifest.json
mode="$(stat -c '%a' /opt/codex/auth.json)"
test "$mode" = "600"
codex --version | grep -F '{CODEX_VERSION}' >/dev/null
CODEX_HOME=/opt/codex codex login status >/dev/null

python - <<'PYCAP'
import json
import os
import urllib.request

request = urllib.request.Request(
    'http://127.0.0.1:8642/v1/capabilities',
    headers={{'Authorization': 'Bearer ' + os.environ['CODEX_RUNNER_API_KEY']}},
)
with urllib.request.urlopen(request, timeout=5) as response:
    payload = json.load(response)
if payload.get('provider') != 'openai-codex-cli':
    raise SystemExit('unexpected runner provider')
if payload.get('authenticated') is not True:
    raise SystemExit('runner reports unauthenticated Codex')
if payload.get('default_model') != 'gpt-5.6-terra':
    raise SystemExit('unexpected default model')
if payload.get('models') != {models_json}:
    raise SystemExit('unexpected model set')
if payload.get('structured_output') is not True:
    raise SystemExit('structured output schema is not active')
PYCAP

python - <<'PYCONTEXT'
import hashlib
import json
from pathlib import Path

root = Path('/opt/codex')
manifest = json.loads((root / 'context-manifest.json').read_text(encoding='utf-8'))
if manifest.get('entity_id') != '{target.project}-coder':
    raise SystemExit('unexpected Codex entity context')
outputs = {{item['path']: item for item in manifest.get('outputs', [])}}
for output_name, path in (
    ('CODEX.AGENTS.md', root / 'AGENTS.md'),
    ('output.schema.json', root / 'output.schema.json'),
):
    record = outputs.get(output_name) or {{}}
    if hashlib.sha256(path.read_bytes()).hexdigest() != record.get('sha256'):
        raise SystemExit('Codex context hash mismatch: ' + output_name)
PYCONTEXT

test -n "${{GH_TOKEN:-}}"
gh api user --jq .login >/dev/null
actual_repo="$(gh api repos/{repository} --jq .full_name)"
test "$actual_repo" = "{repository}"
push_allowed="$(gh api repos/{repository} --jq '.permissions.push')"
test "$push_allowed" = "true"
remote="$(git -C /workspace remote get-url origin)"
case "$remote" in
  {https_remote}|{https_remote}.git) ;;
  *) echo "unexpected Codex origin remote for {target.project}" >&2; exit 41 ;;
esac
git -C /workspace push --dry-run origin \
  HEAD:refs/heads/codex-auth-smoke-{target.project} >/dev/null

fingerprint_before="$(git -C /workspace status --porcelain=v1 --untracked-files=all | sha256sum)"
unshare --user --map-root-user true
unshare --user --map-root-user --mount true
bwrap --unshare-user --unshare-pid --ro-bind / / --proc /proc true
bwrap --unshare-user --ro-bind /workspace /workspace \
  git -C /workspace status --short >/dev/null
fingerprint_after="$(git -C /workspace status --porcelain=v1 --untracked-files=all | sha256sum)"
test "$fingerprint_before" = "$fingerprint_after"
awk '$1 == "NoNewPrivs:" && $2 == "1" {{ok=1}} END {{exit !ok}}' /proc/1/status
awk '$1 == "CapEff:" && $2 == "0000000000000000" {{ok=1}} END {{exit !ok}}' /proc/1/status
awk '$1 == "Seccomp:" && $2 == "2" {{ok=1}} END {{exit !ok}}' /proc/1/status
grep -F 'hermes-codex-bwrap' /proc/1/attr/current >/dev/null
findmnt -n -o OPTIONS / | grep -E '(^|,)ro(,|$)' >/dev/null
"""


def codex_probe_command(target: CoderTarget) -> list[str]:
    return [
        *compose_prefix(),
        "exec",
        "-T",
        target.coder_service,
        "sh",
        "-ceu",
        codex_probe_script(target),
    ]


def verify_github_access(
    target: CoderTarget,
    *,
    runner: Runner = _default_runner,
) -> None:
    run_checked(github_probe_command(target), timeout_seconds=45, runner=runner)


def verify_codex_access(
    target: CoderTarget,
    *,
    runner: Runner = _default_runner,
) -> None:
    auth = ROOT / "codex" / target.project / "auth.json"
    if not auth.is_file() or auth.stat().st_size == 0:
        raise SmokeError(f"Codex auth отсутствует: {auth}")
    mode = stat.S_IMODE(auth.stat().st_mode)
    if mode != 0o600:
        raise SmokeError(f"Codex auth имеет режим {mode:04o}; требуется 0600: {auth}")
    run_checked(codex_probe_command(target), timeout_seconds=60, runner=runner)


def verify_main_cryptography(*, runner: Runner = _default_runner) -> None:
    command = [
        "docker", "compose", "-f", "/srv/velvet/docker-compose.yml",
        "exec", "-T", "bot", "python", "-c",
        "import importlib.metadata as m; print(m.version('cryptography'))",
    ]
    result = run_checked(command, timeout_seconds=30, runner=runner)
    if result.stdout.strip() != CRYPTOGRAPHY_VERSION:
        raise SmokeError(
            "main Hermes cryptography mismatch: expected "
            f"{CRYPTOGRAPHY_VERSION}, actual {redact(result.stdout.strip())}"
        )


def main() -> int:
    for compose_file in COMPOSE_FILES:
        if not compose_file.is_file():
            raise SmokeError(f"Отсутствует Compose-файл: {compose_file}")
    if not ROOT.is_dir():
        raise SmokeError(f"Отсутствует Hermes Coder root: {ROOT}")

    for target in CODERS:
        wait_for_service(target.chat_service)
        wait_for_service(target.coder_service)
        verify_github_access(target)
        verify_codex_access(target)
        print(
            f"Hermes/Codex smoke: {target.project} -> {target.repository}: "
            "CHAT_OK, CODEX_AUTH_OK, LUNA_TERRA_SOL_OK, PUSH_OK"
        )
    verify_main_cryptography()
    print(f"Main Hermes dependency: cryptography=={CRYPTOGRAPHY_VERSION}: OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeError as exc:
        print(f"Hermes Coder runtime smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
