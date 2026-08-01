from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence


ROOT = Path(os.environ.get("HERMES_CODERS_ROOT", "/srv/hermes-coders"))
SOURCE_DIR = Path(__file__).resolve().parent
COMPOSE_FILE = Path(
    os.environ.get("HERMES_CODERS_COMPOSE_FILE", str(SOURCE_DIR / "compose.yaml"))
)
STARTUP_TIMEOUT_SECONDS = max(
    30,
    int(os.environ.get("HERMES_CODERS_SMOKE_TIMEOUT_SECONDS", "180")),
)
POLL_INTERVAL_SECONDS = max(
    1.0,
    float(os.environ.get("HERMES_CODERS_SMOKE_POLL_SECONDS", "3")),
)


@dataclass(frozen=True)
class CoderTarget:
    project: str
    service: str
    repository: str


CODERS = (
    CoderTarget(
        project="velvet",
        service="hermes-coder-velvet",
        repository="Stellmaria/Velvet",
    ),
    CoderTarget(
        project="max",
        service="hermes-coder-max",
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
        "-f",
        str(COMPOSE_FILE),
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


def gateway_probe_command(target: CoderTarget) -> list[str]:
    return [
        *compose_prefix(),
        "exec",
        "-T",
        target.service,
        "python",
        "-c",
        (
            "import urllib.request; "
            "urllib.request.urlopen('http://127.0.0.1:8642/health', timeout=3).read()"
        ),
    ]


def github_probe_script(target: CoderTarget) -> str:
    repository = target.repository
    https_remote = f"https://github.com/{repository}"
    return f"""set -eu

test -n "${{GH_TOKEN:-}}"
test -r /opt/data/config.yaml
python - <<'PYCONFIG'
from pathlib import Path

text = Path('/opt/data/config.yaml').read_text(encoding='utf-8')
if 'env_passthrough:' not in text or '- GH_TOKEN' not in text:
    raise SystemExit('runtime config does not pass GH_TOKEN to terminal')
PYCONFIG

gh api user --jq .login >/dev/null
actual_repo="$(gh api repos/{repository} --jq .full_name)"
test "$actual_repo" = "{repository}"
push_allowed="$(gh api repos/{repository} --jq '.permissions.push')"
test "$push_allowed" = "true"

remote="$(git -C /workspace remote get-url origin)"
case "$remote" in
  {https_remote}|{https_remote}.git) ;;
  *)
    echo "unexpected origin remote for {target.project}" >&2
    exit 31
    ;;
esac

helper="$(git config --global --get credential.https://github.com.helper || true)"
case "$helper" in
  *"gh auth git-credential"*) ;;
  *)
    echo "GitHub credential helper is not configured for {target.project}" >&2
    exit 32
    ;;
esac

git -C /workspace push --dry-run origin \
  HEAD:refs/heads/hermes-auth-smoke-{target.project} >/dev/null
"""


def github_probe_command(target: CoderTarget) -> list[str]:
    return [
        *compose_prefix(),
        "exec",
        "-T",
        target.service,
        "sh",
        "-ceu",
        github_probe_script(target),
    ]


def wait_for_gateway(
    target: CoderTarget,
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
            result = runner(gateway_probe_command(target), 10)
        except (OSError, subprocess.TimeoutExpired) as exc:
            last_details = type(exc).__name__
        else:
            if result.returncode == 0:
                return
            last_details = _result_details(result)
        sleeper(poll_seconds)
    raise SmokeError(
        f"Gateway {target.service} не стал готов за {timeout_seconds} секунд: "
        f"{last_details}"
    )


def verify_github_access(
    target: CoderTarget,
    *,
    runner: Runner = _default_runner,
) -> None:
    run_checked(
        github_probe_command(target),
        timeout_seconds=45,
        runner=runner,
    )


def main() -> int:
    if not COMPOSE_FILE.is_file():
        raise SmokeError(f"Отсутствует Compose-файл: {COMPOSE_FILE}")
    if not ROOT.is_dir():
        raise SmokeError(f"Отсутствует Hermes Coder root: {ROOT}")

    for target in CODERS:
        wait_for_gateway(target)
        verify_github_access(target)
        print(
            f"Hermes Coder GitHub smoke: {target.project} -> "
            f"{target.repository}: AUTH_OK, PUSH_OK"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeError as exc:
        print(f"Hermes Coder runtime smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(2)
