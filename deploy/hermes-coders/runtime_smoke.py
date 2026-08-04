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
    30, int(os.environ.get("HERMES_CODERS_SMOKE_TIMEOUT_SECONDS", "180"))
)
POLL_INTERVAL_SECONDS = max(
    1.0, float(os.environ.get("HERMES_CODERS_SMOKE_POLL_SECONDS", "3"))
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
    CoderTarget("velvet", "hermes-coder-velvet", "hermes-chat-velvet", "Stellmaria/Velvet"),
    CoderTarget("max", "hermes-coder-max", "hermes-chat-max", "Stellmaria/romatic_club_bot_max"),
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


def _default_runner(args: Sequence[str], timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args), check=False, capture_output=True, text=True, timeout=timeout_seconds
    )


def compose_prefix() -> list[str]:
    return [
        "docker", "compose", "--profile", "velvet", "--profile", "max",
        *[part for path in COMPOSE_FILES for part in ("-f", str(path))],
    ]


def _result_details(result: subprocess.CompletedProcess[str]) -> str:
    details = "\n".join(
        part.strip() for part in (result.stderr or "", result.stdout or "") if part.strip()
    )
    return redact(details[:2000]) or "без диагностического вывода"


def run_checked(
    args: Sequence[str], *, timeout_seconds: int, runner: Runner = _default_runner
) -> subprocess.CompletedProcess[str]:
    try:
        result = runner(args, timeout_seconds)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise SmokeError(
            f"Не удалось выполнить {' '.join(args[:4])}: {type(exc).__name__}"
        ) from exc
    if result.returncode != 0:
        raise SmokeError(
            f"Команда завершилась с кодом {result.returncode}: {_result_details(result)}"
        )
    return result


def gateway_probe_command(service: str) -> list[str]:
    return [
        *compose_prefix(), "exec", "-T", service, "python", "-c",
        "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8642/health', timeout=3).read()",
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
    https_remote = f"https://github.com/{target.repository}"
    return f"""set -eu

test -n "${{GH_TOKEN:-}}"
test -r /opt/data/config.yaml
test -r /opt/data/context-manifest.json
gh api user --jq .login >/dev/null
test "$(gh api repos/{target.repository} --jq .full_name)" = "{target.repository}"
test "$(gh api repos/{target.repository} --jq '.permissions.push')" = "true"
remote="$(git -C /workspace remote get-url origin)"
case "$remote" in
  {https_remote}|{https_remote}.git) ;;
  *) echo "unexpected origin remote" >&2; exit 31 ;;
esac
git -C /workspace push --dry-run origin HEAD:refs/heads/hermes-auth-smoke-{target.project} >/dev/null
"""


def codex_probe_script(target: CoderTarget) -> str:
    https_remote = f"https://github.com/{target.repository}"
    models_json = json.dumps(CODEX_MODELS)
    return f"""set -eu

test -s /opt/codex/auth.json
test "$HOME" = "/opt/codex"
test -r /opt/codex/AGENTS.md
test -r /opt/codex/output.schema.json
test -r /opt/codex/context-manifest.json
test -d /workspace-base
test ! -e /workspace
test -S /run/hermes-sandbox/launcher.sock
test "$(stat -c '%a' /opt/codex/auth.json)" = "600"
codex --version | grep -F '{CODEX_VERSION}' >/dev/null
CODEX_HOME=/opt/codex codex login status >/dev/null

python - <<'PYCAP'
import json
import os
import urllib.request
from sandbox_launcher_client import SandboxLauncherClient

request = urllib.request.Request(
    'http://127.0.0.1:8642/v1/capabilities',
    headers={{'Authorization': 'Bearer ' + os.environ['CODEX_RUNNER_API_KEY']}},
)
with urllib.request.urlopen(request, timeout=5) as response:
    payload = json.load(response)
assert payload.get('provider') == 'openai-codex-cli'
assert payload.get('authenticated') is True
assert payload.get('default_model') == 'gpt-5.6-terra'
assert payload.get('models') == {models_json}
assert payload.get('structured_output') is True
assert payload.get('execution_backend') == 'host-sandbox-launcher'
isolation = payload.get('routing', {{}}).get('workspace_isolation', {{}})
assert isolation.get('per_run_clone') is True
assert isolation.get('base_checkout_read_only') is True
sandbox = payload.get('routing', {{}}).get('sandbox', {{}})
assert sandbox.get('boundary') == 'disposable-docker-container'
assert sandbox.get('nested_bwrap') is False
client = SandboxLauncherClient()
ping = client.ping()
assert ping.get('backend') == 'host-docker-launcher'
assert ping.get('nested_bwrap') is False
client.probe('{target.project}')
PYCAP

remote="$(git -C /workspace-base remote get-url origin)"
case "$remote" in
  {https_remote}|{https_remote}.git) ;;
  *) echo "unexpected Codex origin remote" >&2; exit 41 ;;
esac
base_fingerprint() {{
  {{
    git -C /workspace-base rev-parse HEAD
    git -C /workspace-base rev-parse --abbrev-ref HEAD
    git -C /workspace-base for-each-ref --format='%(refname)%00%(objectname)%00' refs/heads refs/tags
    git -C /workspace-base status --porcelain=v1 -z --untracked-files=all
  }} | sha256sum
}}
fingerprint_before="$(base_fingerprint)"
findmnt -n -o OPTIONS /workspace-base | grep -E '(^|,)ro(,|$)' >/dev/null
probe="/opt/codex-runs/smoke-{target.project}-$$"
trap 'rm -rf -- "$probe"' EXIT
rm -rf -- "$probe"
default_branch="$(GIT_TERMINAL_PROMPT=0 git ls-remote --symref "$remote" HEAD | sed -n 's#^ref: refs/heads/\\([^[:space:]]*\\)[[:space:]]*HEAD$#\1#p' | head -n 1)"
test -n "$default_branch"
git check-ref-format --branch "$default_branch" >/dev/null
GIT_TERMINAL_PROMPT=0 git clone --filter=blob:none --no-checkout --single-branch --branch "$default_branch" "$remote" "$probe" >/dev/null
git -C "$probe" checkout --detach --force "origin/$default_branch" >/dev/null
git -C "$probe" push --dry-run origin HEAD:refs/heads/codex-auth-smoke-{target.project} >/dev/null
test "$(base_fingerprint)" = "$fingerprint_before"
awk '$1 == "NoNewPrivs:" && $2 == "1" {{ok=1}} END {{exit !ok}}' /proc/1/status
awk '$1 == "CapEff:" && $2 == "0000000000000000" {{ok=1}} END {{exit !ok}}' /proc/1/status
awk '$1 == "Seccomp:" && $2 == "2" {{ok=1}} END {{exit !ok}}' /proc/1/status
grep -F 'hermes-codex-runner' /proc/1/attr/current >/dev/null
findmnt -n -o OPTIONS / | grep -E '(^|,)ro(,|$)' >/dev/null
if ps -eo stat= | grep -Eq '^Z'; then
  echo "coder container contains zombie processes" >&2
  exit 42
fi
"""


def probe_command(target: CoderTarget, *, coder: bool) -> list[str]:
    script = codex_probe_script(target) if coder else github_probe_script(target)
    service = target.coder_service if coder else target.chat_service
    return [*compose_prefix(), "exec", "-T", service, "sh", "-ceu", script]


def verify_target(target: CoderTarget, *, runner: Runner = _default_runner) -> None:
    auth = ROOT / "codex" / target.project / "auth.json"
    if not auth.is_file() or auth.stat().st_size == 0:
        raise SmokeError(f"Codex auth отсутствует: {auth}")
    mode = stat.S_IMODE(auth.stat().st_mode)
    if mode != 0o600:
        raise SmokeError(f"Codex auth имеет режим {mode:04o}; требуется 0600: {auth}")
    run_checked(probe_command(target, coder=False), timeout_seconds=45, runner=runner)
    run_checked(probe_command(target, coder=True), timeout_seconds=120, runner=runner)


def verify_main_cryptography(*, runner: Runner = _default_runner) -> None:
    command = [
        "docker", "compose", "--env-file", "/srv/velvet/.env.server",
        "-f", "/srv/velvet/docker-compose.server.yml", "exec", "-T", "hermes",
        "python", "-c", "import importlib.metadata as m; print(m.version('cryptography'))",
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
        verify_target(target)
        print(
            f"Hermes/Codex smoke: {target.project} -> {target.repository}: "
            "CHAT_OK, CODEX_AUTH_OK, LAUNCHER_OK, DISPOSABLE_DOCKER_OK, "
            "BASE_RO_OK, PUSH_OK, NO_ZOMBIES"
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
