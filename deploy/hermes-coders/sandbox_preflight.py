#!/usr/bin/env python3
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

from sandbox_launcher_client import LauncherClientError, SandboxLauncherClient

ROOT = Path(os.environ.get("HERMES_CODERS_ROOT", "/srv/hermes-coders"))
SOURCE = Path(__file__).resolve().parent
INSTALL_ROOT = Path(
    os.environ.get(
        "HERMES_SANDBOX_INSTALL_DIR",
        "/usr/local/lib/hermes-sandbox-launcher",
    )
)
NETWORK = os.environ.get(
    "HERMES_SANDBOX_NETWORK", "hermes-sandbox-egress"
).strip()
IMAGES = (
    "velvet-codex-coder-velvet:local",
    "velvet-codex-coder-max:local",
)


class SandboxPreflightError(RuntimeError):
    pass


def require_file(path: Path) -> None:
    if not path.is_file():
        raise SandboxPreflightError(f"Отсутствует sandbox-файл: {path}")


def require_private(path: Path) -> None:
    require_file(path)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o007:
        raise SandboxPreflightError(
            f"Sandbox config доступен посторонним: {path} ({mode:04o})"
        )


def run_checked(args: list[str], message: str) -> None:
    result = subprocess.run(
        args,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        raise SandboxPreflightError(message)


def main() -> int:
    for path in (
        SOURCE / "codex_launcher_runner.py",
        SOURCE / "sandbox_launcher_client.py",
        SOURCE / "sandbox_preflight.py",
        SOURCE / "security" / "apparmor-hermes-codex-runner",
        SOURCE / "security" / "apparmor-hermes-codex-run",
        INSTALL_ROOT / "launcher.py",
        INSTALL_ROOT / "launcher_contract.py",
        INSTALL_ROOT / "launcher_runtime.py",
        INSTALL_ROOT / "sandbox_entrypoint.py",
        Path("/etc/apparmor.d/hermes-codex-runner"),
        Path("/etc/apparmor.d/hermes-codex-run"),
        Path("/etc/systemd/system/hermes-sandbox-launcher.socket"),
        Path("/etc/systemd/system/hermes-sandbox-launcher.service"),
    ):
        require_file(path)
    require_private(ROOT / "launcher.env")

    runtime = (SOURCE / "compose.runtime.yaml").read_text(encoding="utf-8")
    security = (SOURCE / "compose.security.yaml").read_text(encoding="utf-8")
    required_runtime = (
        "CODEX_EXECUTION_BACKEND: launcher",
        "HERMES_SANDBOX_LAUNCHER_SOCKET",
        "codex_launcher_runner.py",
        "sandbox_launcher_client.py",
        "launcher.sock",
    )
    missing = [value for value in required_runtime if value not in runtime]
    if missing:
        raise SandboxPreflightError(
            "compose.runtime не содержит launcher contract: " + ", ".join(missing)
        )
    if security.count("apparmor=hermes-codex-runner") != 2:
        raise SandboxPreflightError(
            "compose.security должен применять runner AppArmor к двум coder services"
        )
    for forbidden in (
        "hermes-codex-bwrap",
        "seccomp-bwrap",
        "seccomp=unconfined",
        "apparmor=unconfined",
        "privileged: true",
    ):
        if forbidden in runtime or forbidden in security:
            raise SandboxPreflightError(
                f"Active Compose всё ещё содержит запрещённый sandbox marker: {forbidden}"
            )

    run_checked(
        ["docker", "network", "inspect", NETWORK],
        f"Dedicated sandbox network недоступна: {NETWORK}",
    )
    for image in IMAGES:
        run_checked(
            ["docker", "image", "inspect", image],
            f"Pinned sandbox image недоступен: {image}",
        )

    socket_path = Path("/run/hermes-sandbox/launcher.sock")
    if not socket_path.exists() or not stat.S_ISSOCK(socket_path.stat().st_mode):
        raise SandboxPreflightError(f"Launcher socket недоступен: {socket_path}")
    socket_mode = stat.S_IMODE(socket_path.stat().st_mode)
    if socket_mode != 0o660:
        raise SandboxPreflightError(
            f"Launcher socket имеет неверный режим {socket_mode:04o}; требуется 0660"
        )
    try:
        payload = SandboxLauncherClient(str(socket_path)).ping()
    except LauncherClientError as error:
        raise SandboxPreflightError(str(error)) from error
    if payload.get("backend") != "host-docker-launcher":
        raise SandboxPreflightError("Launcher сообщил неожиданный backend")
    if payload.get("nested_bwrap") is not False:
        raise SandboxPreflightError("Launcher не подтвердил Docker-only boundary")
    if payload.get("network") != NETWORK:
        raise SandboxPreflightError("Launcher использует неожиданную Docker network")

    print("Hermes sandbox preflight: OK")
    print("- execution backend: host-sandbox-launcher")
    print("- boundary: disposable Docker container")
    print(f"- dedicated network: {NETWORK}")
    print("- pinned images: Velvet and Max")
    print("- nested bwrap: disabled")
    print("- local execution fallback: explicit operator gate only")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SandboxPreflightError, OSError, subprocess.TimeoutExpired) as error:
        print(f"Hermes sandbox preflight failed: {error}", file=sys.stderr)
        raise SystemExit(2)
