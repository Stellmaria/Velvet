from __future__ import annotations

import hmac
import json
import logging
import os
import socket
import socketserver
import stat
import struct
import subprocess
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("velvet.server_supervisor")
_MAX_BODY_BYTES = 64 * 1024
_PEER_CREDENTIALS_SIZE = struct.calcsize("3i")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer.") from error
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _env_mode(name: str, default: int) -> int:
    raw = os.getenv(name, f"{default:04o}").strip()
    try:
        value = int(raw, 8)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an octal filesystem mode.") from error
    if value != 0o660:
        raise RuntimeError(f"{name} must be exactly 0660.")
    return value


def _public_error_code(error: BaseException) -> str:
    name = type(error).__name__
    normalized = "".join(
        character.lower() if character.isalnum() else "_" for character in name
    ).strip("_")
    return normalized or "operation_error"


class OperationConflict(RuntimeError):
    pass


class PublicRequestError(RuntimeError):
    pass


class ServerSupervisorRuntime:
    """Host-side fixed-action supervisor for the Docker production stack."""

    def __init__(self) -> None:
        self.app_dir = Path(os.getenv("VELVET_APP_DIR", "/srv/velvet")).resolve()
        self.env_file = os.getenv("VELVET_ENV_FILE", ".env.server").strip() or ".env.server"
        self.compose_file = (
            os.getenv("VELVET_COMPOSE_FILE", "docker-compose.server.yml").strip()
            or "docker-compose.server.yml"
        )
        self.data_dir = Path(
            os.getenv("VELVET_DATA_DIR", "/srv/velvet/data")
        ).resolve()
        self.runtime_dir = self.data_dir / "runtime" / "supervisor"
        self.control_dir = self.data_dir / "control" / "supervisor"
        self.socket_path = Path(
            os.getenv(
                "SERVER_SUPERVISOR_SOCKET_HOST",
                str(self.control_dir / "velvet-server-supervisor.sock"),
            )
        ).expanduser()
        if not self.socket_path.is_absolute():
            raise RuntimeError("SERVER_SUPERVISOR_SOCKET_HOST must be absolute.")
        if self.socket_path.parent != self.control_dir:
            raise RuntimeError(
                "SERVER_SUPERVISOR_SOCKET_HOST must be inside "
                "VELVET_DATA_DIR/control/supervisor."
            )
        self.socket_client_uid = _env_int(
            "SERVER_SUPERVISOR_CLIENT_UID",
            10001,
            minimum=1,
            maximum=2**31 - 1,
        )
        self.socket_client_gid = _env_int(
            "SERVER_SUPERVISOR_CLIENT_GID",
            -1,
            minimum=1,
            maximum=2**31 - 1,
        )
        self.socket_mode = _env_mode("SERVER_SUPERVISOR_SOCKET_MODE", 0o660)
        self.auth_failure_limit = _env_int(
            "SERVER_SUPERVISOR_AUTH_FAILURE_LIMIT",
            5,
            minimum=1,
            maximum=100,
        )
        self.auth_failure_window_seconds = _env_int(
            "SERVER_SUPERVISOR_AUTH_FAILURE_WINDOW_SECONDS",
            60,
            minimum=10,
            maximum=3600,
        )
        self.auth_failure_cooldown_seconds = _env_int(
            "SERVER_SUPERVISOR_AUTH_FAILURE_COOLDOWN_SECONDS",
            120,
            minimum=10,
            maximum=86400,
        )
        self.state_path = self.runtime_dir / "server-supervisor-state.json"
        self.log_path = self.data_dir / "logs" / "server-supervisor.log"
        self.api_token = os.getenv("SUPERVISOR_TOKEN", "").strip()
        if len(self.api_token) < 24:
            raise RuntimeError("SUPERVISOR_TOKEN must contain at least 24 characters.")
        self.command_timeout = max(
            60,
            min(
                int(os.getenv("SUPERVISOR_COMMAND_TIMEOUT_SECONDS", "1800")),
                7200,
            ),
        )
        self.health_attempts = max(
            1,
            min(int(os.getenv("VELVET_HEALTH_ATTEMPTS", "60")), 180),
        )
        self.health_interval = max(
            1,
            min(int(os.getenv("VELVET_HEALTH_INTERVAL", "5")), 30),
        )
        self._lock = threading.RLock()
        self._auth_lock = threading.Lock()
        self._auth_failures: dict[tuple[int, int], deque[float]] = {}
        self._auth_blocked_until: dict[tuple[int, int], float] = {}
        self._active_operation_id: str | None = None
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()

    def peer_allowed(self, peer: tuple[int, int]) -> bool:
        uid, gid = peer
        return uid == 0 or (
            uid == self.socket_client_uid and gid == self.socket_client_gid
        )

    def auth_blocked(self, peer: tuple[int, int]) -> bool:
        now = time.monotonic()
        with self._auth_lock:
            blocked_until = self._auth_blocked_until.get(peer, 0.0)
            if blocked_until <= now:
                self._auth_blocked_until.pop(peer, None)
                return False
            return True

    def record_auth_failure(self, peer: tuple[int, int]) -> int:
        now = time.monotonic()
        window_start = now - self.auth_failure_window_seconds
        with self._auth_lock:
            failures = self._auth_failures.setdefault(peer, deque())
            while failures and failures[0] < window_start:
                failures.popleft()
            failures.append(now)
            if len(failures) < self.auth_failure_limit:
                return 0
            self._auth_failures.pop(peer, None)
            blocked_until = now + self.auth_failure_cooldown_seconds
            self._auth_blocked_until[peer] = blocked_until
            return self.auth_failure_cooldown_seconds

    def reset_auth_failures(self, peer: tuple[int, int]) -> None:
        with self._auth_lock:
            self._auth_failures.pop(peer, None)
            self._auth_blocked_until.pop(peer, None)

    def _load_state(self) -> dict[str, Any]:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            value = {}
        if not isinstance(value, dict):
            value = {}
        history = value.get("operations")
        if not isinstance(history, list):
            value["operations"] = []
        return value

    def _save_state(self) -> None:
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._state, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        temporary.replace(self.state_path)
        os.chmod(self.state_path, 0o600)

    def _run(
        self,
        command: list[str],
        *,
        timeout: int | None = None,
        check: bool = True,
        extra_env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        if extra_env:
            environment.update(extra_env)
        completed = subprocess.run(
            command,
            cwd=self.app_dir,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout or self.command_timeout,
            check=False,
        )
        if check and completed.returncode != 0:
            output = completed.stdout[-8000:].strip()
            raise RuntimeError(
                f"Command failed ({completed.returncode}): {' '.join(command)}\n{output}"
            )
        return completed

    def _compose(self, *arguments: str) -> list[str]:
        return [
            "docker",
            "compose",
            "--env-file",
            self.env_file,
            "-f",
            self.compose_file,
            *arguments,
        ]

    def _git_value(self, *arguments: str) -> str:
        result = self._run(["git", *arguments], timeout=30)
        return result.stdout.strip()

    def status(self) -> dict[str, Any]:
        bot: dict[str, Any] = {
            "running": False,
            "pid": None,
            "auto_restart": True,
            "crash_loop_open": False,
            "restart_count_in_window": 0,
            "restart_limit": 0,
        }
        try:
            container_id = self._run(
                self._compose("ps", "-q", "bot"), timeout=30
            ).stdout.strip()
            if container_id:
                raw = self._run(
                    ["docker", "inspect", container_id], timeout=30
                ).stdout
                inspection = json.loads(raw)[0]
                state = inspection.get("State", {})
                bot.update(
                    {
                        "running": bool(state.get("Running")),
                        "pid": state.get("Pid"),
                        "status": state.get("Status"),
                        "health": (state.get("Health") or {}).get("Status"),
                        "restart_count_in_window": int(
                            inspection.get("RestartCount", 0) or 0
                        ),
                    }
                )
        except Exception:
            logger.exception("Server Supervisor bot status probe failed")
            bot["error"] = "Bot status probe failed."

        git: dict[str, Any] = {}
        try:
            git["branch"] = self._git_value("branch", "--show-current") or "detached"
            git["head_sha"] = self._git_value("rev-parse", "HEAD")
            git["dirty"] = bool(
                self._git_value("status", "--porcelain", "--untracked-files=no")
            )
            remote = os.getenv("VELVET_DEPLOY_REMOTE", "origin").strip() or "origin"
            branch = os.getenv("VELVET_DEPLOY_BRANCH", "main").strip() or "main"
            remote_ref = f"{remote}/{branch}"
            remote_head = self._run(
                ["git", "rev-parse", "--verify", remote_ref],
                timeout=30,
                check=False,
            )
            if remote_head.returncode == 0:
                git["remote_head_sha"] = remote_head.stdout.strip()
                git["update_available"] = (
                    git["remote_head_sha"] != git["head_sha"]
                )
        except Exception:
            logger.exception("Server Supervisor git status probe failed")
            git["error"] = "Git status probe failed."

        with self._lock:
            operation = self._state.get("last_operation")
        return {
            "supervisor": {
                "pid": os.getpid(),
                "runtime": "server-systemd",
                "deprecated_windows_runtime": "velvet_supervisor",
            },
            "bot": bot,
            "git": git,
            "operation": operation,
            "codex": {"enabled": False},
            "capabilities": {
                "restart": True,
                "update": True,
                "rollback": bool(self._state.get("rollback_sha")),
                "logs": True,
                "console": False,
                "codex": False,
            },
        }

    def log_tail(self, lines: int) -> str:
        safe_lines = max(1, min(int(lines), 2000))
        completed = self._run(
            self._compose("logs", "--no-color", "--tail", str(safe_lines), "bot"),
            timeout=60,
            check=False,
        )
        return completed.stdout[-200_000:]

    def operation_history(self, limit: int) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 100))
        with self._lock:
            history = list(self._state.get("operations", []))
        return history[:safe_limit]

    def schedule_restart(self) -> dict[str, Any]:
        return self._schedule("restart", self._restart_bot)

    def schedule_update(self) -> dict[str, Any]:
        return self._schedule("update", self._deploy_main, restart_daemon=True)

    def schedule_rollback(self, target_sha: str | None = None) -> dict[str, Any]:
        with self._lock:
            target = (target_sha or self._state.get("rollback_sha") or "").strip()
        if not target:
            raise PublicRequestError(
                "No verified previous deployment commit is recorded."
            )
        return self._schedule(
            "rollback",
            lambda: self._deploy_target(target),
            restart_daemon=True,
        )

    def schedule_self_restart(self, *, update: bool) -> dict[str, Any]:
        if update:
            return self.schedule_update()
        return self._schedule(
            "self_restart",
            lambda: "Server Supervisor restarted.",
            restart_daemon=True,
        )

    def _schedule(
        self,
        kind: str,
        action: Any,
        *,
        restart_daemon: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            if self._active_operation_id is not None:
                raise OperationConflict("Another Server Supervisor operation is running.")
            operation = {
                "id": uuid.uuid4().hex[:16],
                "kind": kind,
                "status": "queued",
                "created_at": _utc_now(),
                "started_at": None,
                "completed_at": None,
                "message": "Operation queued.",
                "error": None,
                "error_code": None,
            }
            self._active_operation_id = operation["id"]
            self._record_operation(operation)
        thread = threading.Thread(
            target=self._execute_operation,
            args=(operation, action, restart_daemon),
            name=f"server-supervisor-{kind}",
            daemon=True,
        )
        thread.start()
        return dict(operation)

    def _record_operation(self, operation: dict[str, Any]) -> None:
        history = [
            item
            for item in self._state.get("operations", [])
            if item.get("id") != operation.get("id")
        ]
        self._state["operations"] = [dict(operation), *history][:100]
        self._state["last_operation"] = dict(operation)
        self._save_state()

    def _execute_operation(
        self,
        operation: dict[str, Any],
        action: Any,
        restart_daemon: bool,
    ) -> None:
        operation.update(
            status="running",
            started_at=_utc_now(),
            message="Operation is running.",
        )
        with self._lock:
            self._record_operation(operation)
        try:
            message = str(action() or "Operation completed.")
        except Exception as error:
            error_code = _public_error_code(error)
            logger.exception(
                "Server Supervisor operation failed kind=%s code=%s",
                operation["kind"],
                error_code,
            )
            operation.update(
                status="error",
                completed_at=_utc_now(),
                message="Operation failed.",
                error="Operation failed. See protected Server Supervisor log.",
                error_code=error_code,
            )
        else:
            operation.update(
                status="success",
                completed_at=_utc_now(),
                message=message[-4000:],
                error=None,
                error_code=None,
            )
        finally:
            with self._lock:
                self._active_operation_id = None
                self._record_operation(operation)
        if restart_daemon and operation["status"] == "success":
            time.sleep(1.5)
            os._exit(75)

    def _restart_bot(self) -> str:
        time.sleep(1.5)
        self._run(self._compose("restart", "bot"), timeout=180)
        self._run(
            [
                "bash",
                "deploy/server/wait-compose-health.sh",
                "bot",
                str(self.health_attempts),
                str(self.health_interval),
            ],
            timeout=self.health_attempts * self.health_interval + 60,
            extra_env={
                "VELVET_APP_DIR": str(self.app_dir),
                "VELVET_ENV_FILE": self.env_file,
                "VELVET_COMPOSE_FILE": self.compose_file,
            },
        )
        return "Velvet bot container restarted and became healthy."

    def _deploy_main(self) -> str:
        previous_sha = self._git_value("rev-parse", "HEAD")
        output = self._run(
            ["bash", "deploy/server/deploy.sh"],
            timeout=self.command_timeout,
            extra_env={
                "VELVET_APP_DIR": str(self.app_dir),
                "VELVET_ENV_FILE": self.env_file,
                "VELVET_COMPOSE_FILE": self.compose_file,
            },
        ).stdout
        current_sha = self._git_value("rev-parse", "HEAD")
        with self._lock:
            if current_sha != previous_sha:
                self._state["rollback_sha"] = previous_sha
                self._state["deployed_sha"] = current_sha
                self._save_state()
        return output[-4000:].strip() or f"Velvet updated to {current_sha}."

    def _deploy_target(self, target_sha: str) -> str:
        current_sha = self._git_value("rev-parse", "HEAD")
        output = self._run(
            ["bash", "deploy/server/deploy.sh"],
            timeout=self.command_timeout,
            extra_env={
                "VELVET_APP_DIR": str(self.app_dir),
                "VELVET_ENV_FILE": self.env_file,
                "VELVET_COMPOSE_FILE": self.compose_file,
                "VELVET_DEPLOY_TARGET_SHA": target_sha,
            },
        ).stdout
        deployed_sha = self._git_value("rev-parse", "HEAD")
        with self._lock:
            self._state["rollback_sha"] = current_sha
            self._state["deployed_sha"] = deployed_sha
            self._save_state()
        return output[-4000:].strip() or f"Velvet rolled back to {deployed_sha}."


def prepare_socket_path(runtime: ServerSupervisorRuntime) -> None:
    parent = runtime.socket_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    parent_stat = parent.lstat()
    if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        raise RuntimeError("Server Supervisor control path must be a real directory.")
    if parent_stat.st_uid != os.getuid():
        raise RuntimeError("Server Supervisor control directory has an unexpected owner.")
    try:
        os.chown(parent, -1, runtime.socket_client_gid)
        os.chmod(parent, 0o750)
    except OSError as error:
        raise RuntimeError(
            "Could not apply Server Supervisor control directory ownership."
        ) from error

    try:
        existing = runtime.socket_path.lstat()
    except FileNotFoundError:
        return
    existing_mode = stat.S_IMODE(existing.st_mode)
    if (
        not stat.S_ISSOCK(existing.st_mode)
        or existing.st_uid != os.getuid()
        or existing.st_gid != runtime.socket_client_gid
        or existing_mode != runtime.socket_mode
    ):
        raise RuntimeError(
            "Refusing to replace stale Server Supervisor path with unexpected "
            "type, owner, group or mode."
        )
    runtime.socket_path.unlink()


def secure_socket_path(runtime: ServerSupervisorRuntime) -> None:
    os.chown(runtime.socket_path, os.getuid(), runtime.socket_client_gid)
    os.chmod(runtime.socket_path, runtime.socket_mode)
    value = runtime.socket_path.lstat()
    mode = stat.S_IMODE(value.st_mode)
    if (
        not stat.S_ISSOCK(value.st_mode)
        or value.st_uid != os.getuid()
        or value.st_gid != runtime.socket_client_gid
        or mode != runtime.socket_mode
        or mode & 0o007
    ):
        raise RuntimeError("Server Supervisor socket security contract was not applied.")


class ThreadingUnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, socket_path: str, runtime: ServerSupervisorRuntime) -> None:
        self.runtime = runtime
        super().__init__(socket_path, ServerSupervisorRequestHandler)


class ServerSupervisorRequestHandler(BaseHTTPRequestHandler):
    server: ThreadingUnixHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("Server Supervisor API - %s", format % args)

    def _peer_credentials(self) -> tuple[int, int]:
        if not hasattr(socket, "SO_PEERCRED"):
            raise PermissionError("Unix peer credentials are unavailable.")
        raw = self.connection.getsockopt(
            socket.SOL_SOCKET,
            socket.SO_PEERCRED,
            _PEER_CREDENTIALS_SIZE,
        )
        _pid, uid, gid = struct.unpack("3i", raw)
        return int(uid), int(gid)

    def _require_peer(self) -> tuple[int, int] | None:
        try:
            peer = self._peer_credentials()
        except (OSError, PermissionError, struct.error):
            logger.warning("Server Supervisor denied connection without peer credentials")
            self._send(
                HTTPStatus.FORBIDDEN,
                {
                    "ok": False,
                    "error": "Supervisor peer is not allowed.",
                    "error_code": "peer_forbidden",
                },
            )
            return None
        if self.server.runtime.peer_allowed(peer):
            return peer
        logger.warning(
            "Server Supervisor denied peer uid=%s gid=%s",
            peer[0],
            peer[1],
        )
        self._send(
            HTTPStatus.FORBIDDEN,
            {
                "ok": False,
                "error": "Supervisor peer is not allowed.",
                "error_code": "peer_forbidden",
            },
        )
        return None

    def _authorized(self) -> bool:
        expected = f"Bearer {self.server.runtime.api_token}"
        provided = self.headers.get("Authorization", "")
        return hmac.compare_digest(provided, expected)

    def _send(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _require_auth(self, peer: tuple[int, int]) -> bool:
        if self.server.runtime.auth_blocked(peer):
            self._send(
                HTTPStatus.TOO_MANY_REQUESTS,
                {
                    "ok": False,
                    "error": "Supervisor authentication is temporarily blocked.",
                    "error_code": "auth_rate_limited",
                },
            )
            return False
        if self._authorized():
            self.server.runtime.reset_auth_failures(peer)
            return True
        cooldown = self.server.runtime.record_auth_failure(peer)
        logger.warning(
            "Server Supervisor authentication failed uid=%s gid=%s path=%s cooldown=%s",
            peer[0],
            peer[1],
            urlparse(self.path).path,
            cooldown,
        )
        self._send(
            HTTPStatus.UNAUTHORIZED,
            {
                "ok": False,
                "error": "Invalid Supervisor token.",
                "error_code": "invalid_token",
            },
        )
        return False

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Invalid Content-Length.") from error
        if length < 0 or length > _MAX_BODY_BYTES:
            raise ValueError("Request body is too large.")
        if not length:
            return {}
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON request must be an object.")
        return value

    @staticmethod
    def _int_query(parsed: Any, name: str, default: int, maximum: int) -> int:
        raw = parse_qs(parsed.query).get(name, [str(default)])[0]
        try:
            value = int(raw)
        except ValueError:
            value = default
        return max(1, min(value, maximum))

    def do_GET(self) -> None:  # noqa: N802
        peer = self._require_peer()
        if peer is None:
            return
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(
                HTTPStatus.OK,
                {"ok": True, "runtime": "server-systemd"},
            )
            return
        if not self._require_auth(peer):
            return
        try:
            if parsed.path == "/v1/status":
                self._send(
                    HTTPStatus.OK,
                    {"ok": True, "status": self.server.runtime.status()},
                )
                return
            if parsed.path == "/v1/logs":
                lines = self._int_query(parsed, "lines", 200, 2000)
                self._send(
                    HTTPStatus.OK,
                    {"ok": True, "lines": self.server.runtime.log_tail(lines)},
                )
                return
            if parsed.path == "/v1/operations":
                limit = self._int_query(parsed, "limit", 20, 100)
                self._send(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "operations": self.server.runtime.operation_history(limit),
                    },
                )
                return
            if parsed.path == "/v1/console":
                self._send(HTTPStatus.OK, {"ok": True, "commands": []})
                return
            if parsed.path == "/v1/codex":
                self._send(HTTPStatus.OK, {"ok": True, "tasks": []})
                return
            self._send(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": "Route not found.",
                    "error_code": "not_found",
                },
            )
        except Exception:
            logger.exception("Server Supervisor GET failed path=%s", parsed.path)
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "ok": False,
                    "error": "Internal Supervisor error.",
                    "error_code": "internal_error",
                },
            )

    def do_POST(self) -> None:  # noqa: N802
        peer = self._require_peer()
        if peer is None or not self._require_auth(peer):
            return
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
            if parsed.path == "/v1/restart":
                self._accepted(self.server.runtime.schedule_restart())
                return
            if parsed.path == "/v1/update":
                self._accepted(self.server.runtime.schedule_update())
                return
            if parsed.path == "/v1/rollback":
                target = str(payload.get("target_sha") or "").strip() or None
                self._accepted(self.server.runtime.schedule_rollback(target))
                return
            if parsed.path == "/v1/self/restart":
                self._accepted(
                    self.server.runtime.schedule_self_restart(update=False)
                )
                return
            if parsed.path == "/v1/self/update":
                self._accepted(
                    self.server.runtime.schedule_self_restart(update=True)
                )
                return
            if parsed.path.startswith("/v1/console/") or parsed.path.startswith(
                "/v1/codex"
            ):
                self._send(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "ok": False,
                        "error": (
                            "Console and Codex actions remain disabled in the "
                            "server Supervisor."
                        ),
                        "error_code": "unsupported_action",
                    },
                )
                return
            self._send(
                HTTPStatus.NOT_FOUND,
                {
                    "ok": False,
                    "error": "Route not found.",
                    "error_code": "not_found",
                },
            )
        except OperationConflict as error:
            self._send(
                HTTPStatus.CONFLICT,
                {
                    "ok": False,
                    "error": str(error),
                    "error_code": "operation_conflict",
                },
            )
        except PublicRequestError as error:
            self._send(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": str(error),
                    "error_code": "invalid_operation",
                },
            )
        except (ValueError, KeyError, json.JSONDecodeError):
            self._send(
                HTTPStatus.BAD_REQUEST,
                {
                    "ok": False,
                    "error": "Invalid Supervisor request.",
                    "error_code": "invalid_request",
                },
            )
        except Exception:
            logger.exception("Server Supervisor POST failed path=%s", parsed.path)
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {
                    "ok": False,
                    "error": "Internal Supervisor error.",
                    "error_code": "internal_error",
                },
            )

    def _accepted(self, operation: dict[str, Any]) -> None:
        self._send(
            HTTPStatus.ACCEPTED,
            {"ok": True, "operation": operation},
        )


def main() -> int:
    runtime = ServerSupervisorRuntime()
    prepare_socket_path(runtime)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(runtime.log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    server = ThreadingUnixHTTPServer(str(runtime.socket_path), runtime)
    try:
        secure_socket_path(runtime)
    except Exception:
        server.server_close()
        runtime.socket_path.unlink(missing_ok=True)
        raise
    logger.info(
        "Velvet Server Supervisor listening on %s mode=%04o peer_uid=%s peer_gid=%s",
        runtime.socket_path,
        runtime.socket_mode,
        runtime.socket_client_uid,
        runtime.socket_client_gid,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        try:
            value = runtime.socket_path.lstat()
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISSOCK(value.st_mode) and value.st_uid == os.getuid():
                runtime.socket_path.unlink()
            else:
                logger.error(
                    "Refusing to remove unexpected Server Supervisor socket path"
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
