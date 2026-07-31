from __future__ import annotations

import hmac
import json
import logging
import os
import socketserver
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger("velvet.server_supervisor")
_MAX_BODY_BYTES = 64 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperationConflict(RuntimeError):
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
        self.socket_path = Path(
            os.getenv(
                "SERVER_SUPERVISOR_SOCKET_HOST",
                str(self.runtime_dir / "velvet-server-supervisor.sock"),
            )
        ).resolve()
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
        self._active_operation_id: str | None = None
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._state = self._load_state()

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
        except Exception as error:
            bot["error"] = str(error)

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
        except Exception as error:
            git["error"] = str(error)

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
            raise RuntimeError("No verified previous deployment commit is recorded.")
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
            logger.exception("Server Supervisor operation failed kind=%s", operation["kind"])
            operation.update(
                status="error",
                completed_at=_utc_now(),
                message="Operation failed.",
                error=str(error)[-8000:],
            )
        else:
            operation.update(
                status="success",
                completed_at=_utc_now(),
                message=message[-4000:],
                error=None,
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


class ThreadingUnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, socket_path: str, runtime: ServerSupervisorRuntime) -> None:
        self.runtime = runtime
        super().__init__(socket_path, ServerSupervisorRequestHandler)


class ServerSupervisorRequestHandler(BaseHTTPRequestHandler):
    server: ThreadingUnixHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("Server Supervisor API - %s", format % args)

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

    def _require_auth(self) -> bool:
        if self._authorized():
            return True
        self._send(
            HTTPStatus.UNAUTHORIZED,
            {"ok": False, "error": "Invalid Supervisor token."},
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
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send(
                HTTPStatus.OK,
                {"ok": True, "runtime": "server-systemd"},
            )
            return
        if not self._require_auth():
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
                {"ok": False, "error": "Route not found."},
            )
        except Exception as error:
            logger.exception("Server Supervisor GET failed path=%s", parsed.path)
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": str(error)},
            )

    def do_POST(self) -> None:  # noqa: N802
        if not self._require_auth():
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
                    },
                )
                return
            self._send(
                HTTPStatus.NOT_FOUND,
                {"ok": False, "error": "Route not found."},
            )
        except OperationConflict as error:
            self._send(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": str(error)},
            )
        except (ValueError, RuntimeError, KeyError, json.JSONDecodeError) as error:
            self._send(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": str(error)},
            )
        except Exception as error:
            logger.exception("Server Supervisor POST failed path=%s", parsed.path)
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": str(error)},
            )

    def _accepted(self, operation: dict[str, Any]) -> None:
        self._send(
            HTTPStatus.ACCEPTED,
            {"ok": True, "operation": operation},
        )


def main() -> int:
    runtime = ServerSupervisorRuntime()
    runtime.socket_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        runtime.socket_path.unlink()
    except FileNotFoundError:
        pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(runtime.log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )
    server = ThreadingUnixHTTPServer(str(runtime.socket_path), runtime)
    os.chmod(runtime.socket_path, 0o666)
    logger.info(
        "Velvet Server Supervisor listening on %s",
        runtime.socket_path,
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
        try:
            runtime.socket_path.unlink()
        except FileNotFoundError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
