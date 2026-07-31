from __future__ import annotations

import hmac
import json
import logging
import os
import socketserver
import stat
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("velvet.hermes_operator_host")
_MAX_REQUEST_BYTES = 8 * 1024
_MAX_OUTPUT_BYTES = 16 * 1024


@dataclass(frozen=True, slots=True)
class ServiceTarget:
    app_dir: Path
    env_file: str
    compose_file: str
    services: frozenset[str]


class ConfigurationError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be configured")
    return value


def _targets() -> dict[str, ServiceTarget]:
    return {
        "velvet": ServiceTarget(
            app_dir=Path(os.getenv("VELVET_APP_DIR", "/srv/velvet")).resolve(),
            env_file=os.getenv("VELVET_ENV_FILE", ".env.server").strip()
            or ".env.server",
            compose_file=os.getenv(
                "VELVET_COMPOSE_FILE", "docker-compose.server.yml"
            ).strip()
            or "docker-compose.server.yml",
            services=frozenset({"bot"}),
        ),
        "max": ServiceTarget(
            app_dir=Path(
                os.getenv("ROMATIC_APP_DIR", "/srv/romatic-club-max")
            ).resolve(),
            env_file=os.getenv("ROMATIC_ENV_FILE", ".env").strip() or ".env",
            compose_file=os.getenv("ROMATIC_COMPOSE_FILE", "compose.yaml").strip()
            or "compose.yaml",
            services=frozenset({"bot", "userbot"}),
        ),
    }


class StartRuntime:
    def __init__(self) -> None:
        self.token = _required("HERMES_OPS_HOST_TOKEN")
        if len(self.token) < 24:
            raise ConfigurationError(
                "HERMES_OPS_HOST_TOKEN must contain at least 24 characters"
            )
        self.targets = _targets()
        self.command_timeout = max(
            30,
            min(int(os.getenv("HERMES_OPS_START_TIMEOUT_SECONDS", "300")), 1800),
        )
        self.health_attempts = max(
            1,
            min(int(os.getenv("HERMES_OPS_START_HEALTH_ATTEMPTS", "60")), 180),
        )
        self.health_interval = max(
            1,
            min(int(os.getenv("HERMES_OPS_START_HEALTH_INTERVAL", "2")), 30),
        )
        self._lock = threading.Lock()

    @staticmethod
    def _compose(target: ServiceTarget, *arguments: str) -> list[str]:
        return [
            "docker",
            "compose",
            "--env-file",
            target.env_file,
            "-f",
            target.compose_file,
            *arguments,
        ]

    @staticmethod
    def _run(
        target: ServiceTarget,
        command: list[str],
        *,
        timeout: int,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            cwd=target.app_dir,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        if check and completed.returncode != 0:
            output = completed.stdout[-_MAX_OUTPUT_BYTES:].strip()
            raise RuntimeError(
                f"Fixed start command failed ({completed.returncode}).\n{output}"
            )
        return completed

    def _container_state(
        self,
        target: ServiceTarget,
        service: str,
    ) -> dict[str, Any]:
        container_id = self._run(
            target,
            self._compose(target, "ps", "-q", service),
            timeout=30,
            check=False,
        ).stdout.strip()
        if not container_id:
            return {"running": False, "status": "missing", "health": None}
        raw = self._run(
            target,
            ["docker", "inspect", "--format", "{{json .State}}", container_id],
            timeout=30,
            check=False,
        ).stdout.strip()
        try:
            state = json.loads(raw)
        except (TypeError, ValueError):
            state = {}
        if not isinstance(state, dict):
            state = {}
        health = state.get("Health")
        return {
            "running": bool(state.get("Running")),
            "status": state.get("Status") or "unknown",
            "health": health.get("Status") if isinstance(health, dict) else None,
        }

    def _wait_ready(
        self,
        target: ServiceTarget,
        service: str,
    ) -> dict[str, Any]:
        latest: dict[str, Any] = {}
        for _ in range(self.health_attempts):
            latest = self._container_state(target, service)
            if latest.get("running") is True and latest.get("health") in {
                None,
                "healthy",
            }:
                return latest
            if latest.get("status") in {"dead", "exited"} or latest.get(
                "health"
            ) == "unhealthy":
                break
            time.sleep(self.health_interval)
        raise RuntimeError(
            f"Service did not become healthy: {service}; state={latest}"
        )

    def start(self, project: str, service: str) -> dict[str, Any]:
        target = self.targets.get(project)
        if target is None or service not in target.services:
            return {
                "ok": False,
                "error": "Unknown project or service",
                "error_code": "unknown_target",
            }

        with self._lock:
            before = self._container_state(target, service)
            was_running = before.get("running") is True
            health = before.get("health")
            if was_running and health in {None, "healthy"}:
                return {
                    "ok": True,
                    "project": project,
                    "service": service,
                    "changed": False,
                    "message": "Service is already running",
                    "state": before,
                }
            if was_running and health == "unhealthy":
                raise RuntimeError(
                    f"Service is running but unhealthy: {project}/{service}; "
                    "use explicit restart"
                )
            if not was_running:
                self._run(
                    target,
                    self._compose(
                        target,
                        "up",
                        "-d",
                        "--no-build",
                        "--no-recreate",
                        service,
                    ),
                    timeout=self.command_timeout,
                )
            latest = self._wait_ready(target, service)
            return {
                "ok": True,
                "project": project,
                "service": service,
                "changed": not was_running,
                "message": "Service started and passed runtime check",
                "state": latest,
            }


class StartRequestHandler(socketserver.StreamRequestHandler):
    server: "StartUnixServer"

    def handle(self) -> None:
        raw = self.rfile.readline(_MAX_REQUEST_BYTES + 1)
        if not raw or len(raw) > _MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
            self._send(
                {"ok": False, "error": "Invalid request", "error_code": "invalid"}
            )
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send(
                {"ok": False, "error": "Invalid JSON", "error_code": "invalid"}
            )
            return
        if not isinstance(payload, dict) or set(payload) != {
            "token",
            "project",
            "service",
        }:
            self._send(
                {"ok": False, "error": "Invalid fields", "error_code": "invalid"}
            )
            return
        if not hmac.compare_digest(str(payload["token"]), self.server.runtime.token):
            logger.warning("Denied Hermes operator host start request")
            self._send(
                {
                    "ok": False,
                    "error": "Unauthorized",
                    "error_code": "unauthorized",
                }
            )
            return
        project = str(payload["project"])
        service = str(payload["service"])
        try:
            result = self.server.runtime.start(project, service)
        except Exception:
            logger.exception(
                "Hermes operator fixed start failed project=%s service=%s",
                project,
                service,
            )
            result = {
                "ok": False,
                "error": "Fixed start operation failed",
                "error_code": "start_failed",
            }
        self._send(result)

    def _send(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        self.wfile.write(data)
        self.wfile.flush()


class StartUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, path: str, runtime: StartRuntime) -> None:
        self.runtime = runtime
        super().__init__(path, StartRequestHandler)


def _prepare_socket(path: Path, socket_gid: int) -> None:
    try:
        parent = path.parent.lstat()
    except FileNotFoundError as error:
        raise RuntimeError("Hermes operator runtime directory is missing") from error
    parent_mode = stat.S_IMODE(parent.st_mode)
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != os.getuid()
        or parent.st_gid != socket_gid
        or parent_mode != 0o750
    ):
        raise RuntimeError(
            "Hermes operator runtime directory has unsafe type, owner, group or mode"
        )
    try:
        existing = path.lstat()
    except FileNotFoundError:
        return
    existing_mode = stat.S_IMODE(existing.st_mode)
    if (
        not stat.S_ISSOCK(existing.st_mode)
        or existing.st_uid != os.getuid()
        or existing.st_gid != socket_gid
        or existing_mode != 0o660
    ):
        raise RuntimeError("Refusing to replace unsafe Hermes operator socket")
    path.unlink()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    socket_path = Path(
        os.getenv(
            "HERMES_OPS_HOST_SOCKET",
            "/srv/hermes-operator-control/runtime/start.sock",
        )
    ).resolve()
    expected_parent = Path(
        os.getenv(
            "HERMES_OPS_HOST_RUNTIME_DIR",
            "/srv/hermes-operator-control/runtime",
        )
    ).resolve()
    if socket_path.parent != expected_parent:
        raise ConfigurationError("HERMES_OPS_HOST_SOCKET must be inside runtime dir")
    socket_gid = int(os.getenv("HERMES_OPS_SOCKET_GID", "10001"))
    _prepare_socket(socket_path, socket_gid)
    server = StartUnixServer(str(socket_path), StartRuntime())
    os.chown(socket_path, os.getuid(), socket_gid)
    os.chmod(socket_path, 0o660)
    logger.info("Hermes operator host start bridge listening on %s", socket_path)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()
