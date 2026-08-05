#!/usr/bin/env python3
from __future__ import annotations

import hmac
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

from sandbox_launcher_client import LauncherClientError, SandboxLauncherClient

ROOT = Path(os.environ.get("HERMES_CODERS_ROOT", "/srv/hermes-coders")).resolve()
SOURCE = Path(__file__).resolve().parent
INSTALL_ROOT = Path(
    os.environ.get(
        "HERMES_SANDBOX_INSTALL_ROOT",
        "/usr/local/lib/hermes-sandbox-launcher",
    )
).resolve()
CURRENT = INSTALL_ROOT / "current"
NETWORK = os.environ.get("HERMES_SANDBOX_NETWORK", "hermes-sandbox-egress").strip()
_IMAGE_ID = re.compile(r"^sha256:[0-9a-f]{64}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43,128}$")
_PROJECTS = ("velvet", "max")


class SandboxPreflightError(RuntimeError):
    pass


def parse_env(path: Path) -> dict[str, str]:
    if path.is_symlink() or not path.is_file():
        raise SandboxPreflightError(f"Отсутствует или небезопасен env-файл: {path}")
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, value = line.split("=", 1)
        key = key.strip()
        if key in values:
            raise SandboxPreflightError(f"Повторяющийся env key: {key}")
        values[key] = value.strip().strip('"').strip("'")
    return values


def require_file(path: Path) -> None:
    if path.is_symlink() or not path.is_file():
        raise SandboxPreflightError(f"Отсутствует или небезопасен sandbox-файл: {path}")


def require_mode(path: Path, expected: int) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != expected:
        raise SandboxPreflightError(
            f"Неверный режим {path}: {mode:04o}; требуется {expected:04o}"
        )


def run_checked(args: list[str], message: str, *, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            args,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SandboxPreflightError(message) from error
    if result.returncode != 0:
        raise SandboxPreflightError(message)
    return result.stdout


def verify_release() -> Path:
    if not CURRENT.is_symlink():
        raise SandboxPreflightError(f"Launcher current не является symlink: {CURRENT}")
    release = CURRENT.resolve()
    releases = (INSTALL_ROOT / "releases").resolve()
    if release.parent != releases or not re.fullmatch(r"[0-9a-f]{40}", release.name):
        raise SandboxPreflightError("Launcher current не указывает на exact-SHA release")
    if release.is_symlink() or not release.is_dir():
        raise SandboxPreflightError("Launcher release отсутствует или небезопасен")
    for name in (
        "launcher.py",
        "launcher_contract.py",
        "launcher_runtime.py",
        "sandbox_entrypoint.py",
    ):
        candidate = release / name
        require_file(candidate)
        mode = stat.S_IMODE(candidate.stat().st_mode)
        if mode & 0o022:
            raise SandboxPreflightError(f"Launcher artifact writable: {candidate}")
        if candidate.stat().st_uid != 0 or candidate.stat().st_gid != 0:
            raise SandboxPreflightError(f"Launcher artifact не root-owned: {candidate}")
    return release


def verify_credentials() -> dict[str, str]:
    secrets_path = ROOT / "launcher-secrets.env"
    require_file(secrets_path)
    require_mode(secrets_path, 0o600)
    secret_stat = secrets_path.stat()
    if secret_stat.st_uid != 0 or secret_stat.st_gid != 0:
        raise SandboxPreflightError("launcher-secrets.env должен быть root:root")
    root_values = parse_env(secrets_path)
    expected_keys = {
        "HERMES_SANDBOX_VELVET_TOKEN",
        "HERMES_SANDBOX_MAX_TOKEN",
    }
    if set(root_values) != expected_keys:
        raise SandboxPreflightError(
            "launcher-secrets.env содержит лишние или отсутствующие keys"
        )
    tokens = {
        "velvet": root_values["HERMES_SANDBOX_VELVET_TOKEN"],
        "max": root_values["HERMES_SANDBOX_MAX_TOKEN"],
    }
    if any(not _TOKEN.fullmatch(token) for token in tokens.values()):
        raise SandboxPreflightError("Launcher project token имеет неверный формат")
    if hmac.compare_digest(tokens["velvet"], tokens["max"]):
        raise SandboxPreflightError("Velvet и Max launcher tokens совпадают")
    for project in _PROJECTS:
        project_values = parse_env(ROOT / "secrets" / f"{project}.env")
        project_token = project_values.get("HERMES_SANDBOX_LAUNCHER_TOKEN", "")
        if not hmac.compare_digest(project_token, tokens[project]):
            raise SandboxPreflightError(
                f"Project launcher token не согласован для {project}"
            )
    return tokens


def verify_env_and_images(release: Path) -> None:
    launcher_env = ROOT / "launcher.env"
    require_file(launcher_env)
    mode = stat.S_IMODE(launcher_env.stat().st_mode)
    if mode & 0o007:
        raise SandboxPreflightError("launcher.env доступен посторонним")
    values = parse_env(launcher_env)
    if Path(values.get("HERMES_SANDBOX_INSTALL_DIR", "")).resolve() != release:
        raise SandboxPreflightError("launcher.env не указывает на active exact release")
    pending = Path(values.get("HERMES_SANDBOX_PENDING_INSTALL_DIR", ""))
    if pending.resolve() != release:
        raise SandboxPreflightError("launcher.env pending/current release расходятся")
    if values.get("HERMES_SANDBOX_NETWORK") != NETWORK:
        raise SandboxPreflightError("launcher.env содержит неожиданную network")
    for project, key in (
        ("velvet", "HERMES_SANDBOX_VELVET_IMAGE"),
        ("max", "HERMES_SANDBOX_MAX_IMAGE"),
    ):
        image = values.get(key, "")
        if not _IMAGE_ID.fullmatch(image):
            raise SandboxPreflightError(f"{project} image не является immutable image ID")
        run_checked(
            ["docker", "image", "inspect", image],
            f"Pinned sandbox image недоступен для {project}",
        )


def verify_static_contract() -> None:
    for path in (
        SOURCE / "codex_launcher_runner.py",
        SOURCE / "sandbox_launcher_client.py",
        SOURCE / "sandbox_preflight.py",
        SOURCE / "security" / "apparmor-hermes-codex-runner",
        SOURCE / "security" / "apparmor-hermes-codex-run",
        Path("/etc/apparmor.d/hermes-codex-runner"),
        Path("/etc/apparmor.d/hermes-codex-run"),
        Path("/etc/systemd/system/hermes-sandbox-launcher.socket"),
        Path("/etc/systemd/system/hermes-sandbox-launcher.service"),
    ):
        require_file(path)
    compose = run_checked(
        [
            "docker",
            "compose",
            "--project-name",
            "hermes-coders",
            "--profile",
            "velvet",
            "--profile",
            "max",
            "-f",
            str(SOURCE / "compose.yaml"),
            "-f",
            str(SOURCE / "compose.runtime.yaml"),
            "-f",
            str(SOURCE / "compose.security.yaml"),
            "config",
        ],
        "Rendered Compose contract недоступен",
    )
    required = (
        "CODEX_EXECUTION_BACKEND: launcher",
        "HERMES_SANDBOX_LAUNCHER_SOCKET: /run/hermes-sandbox/launcher.sock",
        "apparmor=hermes-codex-runner",
    )
    for marker in required:
        if marker not in compose:
            raise SandboxPreflightError(f"Rendered Compose не содержит: {marker}")
    for forbidden in (
        "/var/run/docker.sock",
        "/run/docker.sock",
        "privileged: true",
        "seccomp=unconfined",
        "apparmor=unconfined",
        "hermes-codex-bwrap",
    ):
        if forbidden in compose:
            raise SandboxPreflightError(
                f"Rendered Compose содержит запрещённый marker: {forbidden}"
            )
    profiles = Path("/sys/kernel/security/apparmor/profiles")
    if profiles.is_file():
        active = profiles.read_text(encoding="utf-8", errors="replace")
        for profile in ("hermes-codex-runner", "hermes-codex-run"):
            if f"{profile} (enforce)" not in active:
                raise SandboxPreflightError(f"AppArmor profile не enforcing: {profile}")


def verify_socket_and_probes(tokens: dict[str, str]) -> None:
    run_checked(
        ["docker", "network", "inspect", NETWORK],
        f"Dedicated sandbox network недоступна: {NETWORK}",
    )
    socket_path = Path("/run/hermes-sandbox/launcher.sock")
    if not socket_path.exists() or not stat.S_ISSOCK(socket_path.stat().st_mode):
        raise SandboxPreflightError(f"Launcher socket недоступен: {socket_path}")
    require_mode(socket_path, 0o660)
    for project in _PROJECTS:
        previous_project = os.environ.get("HERMES_CODER_PROJECT")
        previous_token = os.environ.get("HERMES_SANDBOX_LAUNCHER_TOKEN")
        os.environ["HERMES_CODER_PROJECT"] = project
        os.environ["HERMES_SANDBOX_LAUNCHER_TOKEN"] = tokens[project]
        try:
            client = SandboxLauncherClient(str(socket_path))
            ping = client.ping()
            probe = client.probe(project)
        except LauncherClientError as error:
            raise SandboxPreflightError(
                f"Authenticated launcher probe отклонён для {project}"
            ) from error
        finally:
            if previous_project is None:
                os.environ.pop("HERMES_CODER_PROJECT", None)
            else:
                os.environ["HERMES_CODER_PROJECT"] = previous_project
            if previous_token is None:
                os.environ.pop("HERMES_SANDBOX_LAUNCHER_TOKEN", None)
            else:
                os.environ["HERMES_SANDBOX_LAUNCHER_TOKEN"] = previous_token
        if ping.get("backend") != "host-docker-launcher":
            raise SandboxPreflightError("Launcher сообщил неожиданный backend")
        if ping.get("nested_bwrap") is not False or ping.get("project_auth") is not True:
            raise SandboxPreflightError("Launcher не подтвердил canonical auth boundary")
        if ping.get("network") != NETWORK:
            raise SandboxPreflightError("Launcher использует неожиданную Docker network")
        if int(probe.get("returncode", 1)) != 0:
            raise SandboxPreflightError(f"Launcher probe failed для {project}")


def main() -> int:
    release = verify_release()
    tokens = verify_credentials()
    verify_env_and_images(release)
    verify_static_contract()
    verify_socket_and_probes(tokens)
    print("Hermes sandbox preflight: PASS")
    print(f"- launcher release: {release.name}")
    print("- project authentication: Velvet/Max distinct and verified")
    print("- images: immutable sha256 IDs")
    print("- boundary: disposable Docker container")
    print("- nested bwrap/local fallback: disabled")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SandboxPreflightError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Hermes sandbox preflight failed: {error}", file=sys.stderr)
        raise SystemExit(2)
