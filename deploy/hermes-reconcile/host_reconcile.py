from __future__ import annotations

import hmac
import json
import logging
import os
import re
import socketserver
import stat
import subprocess
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Sequence

logger = logging.getLogger("velvet.hermes_operator_reconcile")
_MAX_REQUEST_BYTES = 8 * 1024
_MAX_OUTPUT_BYTES = 24 * 1024
_MAX_TASKS = 100
_TARGETS = frozenset({"coders", "entities", "librarian", "all"})
_TERMINAL = frozenset({"completed", "failed"})
_SECRET_PATTERNS = (
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[opsu]_[A-Za-z0-9]+"),
    re.compile(r"(?i)(token\s*[=:]\s*)\S+"),
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)\S+"),
    re.compile(r"(?i)(password\s*[=:]\s*)\S+"),
    re.compile(r"(?i)(api[_-]?key\s*[=:]\s*)\S+"),
)


class ConfigurationError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be configured")
    return value


def _redact(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        replacement = r"\1[redacted]" if pattern.groups else "[redacted]"
        result = pattern.sub(replacement, result)
    return result


def _now() -> str:
    return datetime.now(UTC).isoformat()


class ReconcileRuntime:
    def __init__(self) -> None:
        self.token = _required("HERMES_OPS_RECONCILE_TOKEN")
        if len(self.token) < 24:
            raise ConfigurationError(
                "HERMES_OPS_RECONCILE_TOKEN must contain at least 24 characters"
            )
        self.app_dir = Path(os.getenv("VELVET_APP_DIR", "/srv/velvet")).resolve()
        self.branch = os.getenv("HERMES_OPS_RECONCILE_BRANCH", "main").strip() or "main"
        self.state_dir = Path(
            os.getenv(
                "HERMES_OPS_RECONCILE_STATE_DIR",
                "/srv/hermes-operator-control/reconcile-state",
            )
        ).resolve()
        self.state_file = self.state_dir / "tasks.json"
        self._lock = threading.RLock()
        self._tasks = self._load_tasks()
        self._persist()
        self._steps = self._build_steps()

    def _build_steps(self) -> dict[str, tuple[tuple[str, tuple[str, ...], int], ...]]:
        python = "/usr/bin/python3"
        bash = "/usr/bin/bash"
        systemctl = "/usr/bin/systemctl"
        coders_install = self.app_dir / "deploy/hermes-coders/install.sh"
        coders_smoke = self.app_dir / "deploy/hermes-coders/runtime_smoke.py"
        entities_install = self.app_dir / "deploy/hermes-entities/install.sh"
        librarian_install = self.app_dir / "deploy/hermes-librarian/install.sh"

        coders = (
            ("install-coders", (bash, str(coders_install)), 2400),
            ("enable-coders", (systemctl, "enable", "hermes-coders.service"), 180),
            ("restart-coders", (systemctl, "restart", "hermes-coders.service"), 600),
            ("smoke-coders", (python, str(coders_smoke)), 300),
        )
        librarian = (
            ("install-librarian", (bash, str(librarian_install)), 1800),
        )
        entities = (
            ("install-entities", (bash, str(entities_install)), 1800),
        )
        return {
            "coders": coders,
            "librarian": librarian,
            "entities": entities,
            # Entities restart the main Kael runtime, so they must be last.
            "all": (*coders, *librarian, *entities),
        }

    def _load_tasks(self) -> dict[str, dict[str, Any]]:
        self.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.state_dir, 0o700)
        if not self.state_file.exists():
            return {}
        try:
            value = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ConfigurationError("Hermes reconcile state is unreadable") from error
        if not isinstance(value, dict):
            raise ConfigurationError("Hermes reconcile state must be an object")
        tasks = {
            str(task_id): dict(record)
            for task_id, record in value.items()
            if isinstance(record, dict)
        }
        # A daemon restart cannot resume an in-process installer safely.
        for record in tasks.values():
            if record.get("status") in {"queued", "running"}:
                record["status"] = "failed"
                record["finished_at"] = _now()
                record["error"] = "Reconcile host restarted before task completion"
        return tasks

    def _persist(self) -> None:
        ordered = sorted(
            self._tasks.items(),
            key=lambda item: str(item[1].get("created_at", "")),
            reverse=True,
        )[:_MAX_TASKS]
        self._tasks = dict(ordered)
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(self._tasks, ensure_ascii=False, indent=2, sort_keys=True)
            + "\n",
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.state_file)
        os.chmod(self.state_file, 0o600)

    def _run(
        self,
        command: Sequence[str],
        *,
        timeout: int,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        env = {
            "HOME": "/root",
            "LANG": os.getenv("LANG", "C.UTF-8"),
            "LC_ALL": os.getenv("LC_ALL", "C.UTF-8"),
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "DOCKER_CONFIG": "/srv/hermes-operator-control/reconcile-docker-config",
            "COMPOSE_BAKE": "false",
        }
        completed = subprocess.run(
            list(command),
            cwd=self.app_dir,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        if check and completed.returncode != 0:
            output = _redact((completed.stdout or "")[-_MAX_OUTPUT_BYTES:].strip())
            raise RuntimeError(
                f"Fixed reconcile command failed ({completed.returncode}).\n{output}"
            )
        return completed

    def _git(self, *arguments: str) -> str:
        result = self._run(
            ["/usr/bin/git", "-C", str(self.app_dir), *arguments],
            timeout=90,
        )
        return (result.stdout or "").strip()

    def _verify_checkout(self) -> str:
        if not self.app_dir.is_dir():
            raise RuntimeError("Velvet production checkout is missing")
        top = Path(self._git("rev-parse", "--show-toplevel")).resolve()
        if top != self.app_dir:
            raise RuntimeError("Velvet production checkout root is unexpected")
        branch = self._git("symbolic-ref", "--short", "HEAD")
        if branch != self.branch:
            raise RuntimeError(
                f"Velvet production checkout must be on {self.branch}; got {branch}"
            )
        status = self._git("status", "--porcelain", "--untracked-files=all")
        if status:
            raise RuntimeError("Velvet production checkout is not clean")
        head = self._git("rev-parse", "HEAD")
        remote = self._git("rev-parse", f"refs/remotes/origin/{self.branch}")
        if head != remote:
            raise RuntimeError(
                "Velvet production checkout does not match the fetched origin/main"
            )
        return head

    def _active_task(self) -> dict[str, Any] | None:
        for task_id, record in self._tasks.items():
            if record.get("status") in {"queued", "running"}:
                return {"task_id": task_id, **record}
        return None

    def submit(self, target: str) -> dict[str, Any]:
        if target not in _TARGETS:
            return {
                "ok": False,
                "error": "Unknown reconcile target",
                "error_code": "unknown_target",
            }
        with self._lock:
            active = self._active_task()
            if active is not None:
                return {
                    "ok": False,
                    "error": "Another reconcile task is already active",
                    "error_code": "busy",
                    "active_task": active,
                }
            head = self._verify_checkout()
            task_id = f"reconcile_{uuid.uuid4().hex}"
            record: dict[str, Any] = {
                "target": target,
                "status": "queued",
                "head": head,
                "created_at": _now(),
                "started_at": None,
                "finished_at": None,
                "completed_steps": [],
                "error": None,
            }
            self._tasks[task_id] = record
            self._persist()
            thread = threading.Thread(
                target=self._execute,
                args=(task_id, target, head),
                name=f"hermes-reconcile-{target}",
                daemon=True,
            )
            thread.start()
            return {
                "ok": True,
                "accepted": True,
                "task_id": task_id,
                "target": target,
                "head": head,
                "status": "queued",
            }

    def _execute(self, task_id: str, target: str, head: str) -> None:
        with self._lock:
            record = self._tasks[task_id]
            record["status"] = "running"
            record["started_at"] = _now()
            self._persist()
        try:
            for name, command, timeout in self._steps[target]:
                self._run(command, timeout=timeout)
                with self._lock:
                    self._tasks[task_id]["completed_steps"].append(name)
                    self._persist()
            final_head = self._verify_checkout()
            if final_head != head:
                raise RuntimeError("Velvet checkout changed during reconcile")
        except Exception as error:
            logger.error(
                "Hermes fixed reconcile failed task=%s target=%s: %s",
                task_id,
                target,
                _redact(str(error)),
            )
            with self._lock:
                record = self._tasks[task_id]
                record["status"] = "failed"
                record["finished_at"] = _now()
                record["error"] = _redact(str(error))[-_MAX_OUTPUT_BYTES:]
                self._persist()
            return
        with self._lock:
            record = self._tasks[task_id]
            record["status"] = "completed"
            record["finished_at"] = _now()
            self._persist()

    def status(self, task_id: str) -> dict[str, Any]:
        with self._lock:
            record = self._tasks.get(task_id)
            if record is None:
                return {
                    "ok": False,
                    "error": "Unknown reconcile task",
                    "error_code": "not_found",
                }
            return {"ok": True, "task_id": task_id, **record}

    def list_tasks(self) -> dict[str, Any]:
        with self._lock:
            tasks = [
                {"task_id": task_id, **record}
                for task_id, record in self._tasks.items()
            ]
        return {"ok": True, "tasks": tasks[:20]}


class ReconcileRequestHandler(socketserver.StreamRequestHandler):
    server: "ReconcileUnixServer"

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
        if not isinstance(payload, dict) or "token" not in payload or "action" not in payload:
            self._send(
                {"ok": False, "error": "Invalid fields", "error_code": "invalid"}
            )
            return
        if not hmac.compare_digest(str(payload["token"]), self.server.runtime.token):
            logger.warning("Denied Hermes reconcile request")
            self._send(
                {
                    "ok": False,
                    "error": "Unauthorized",
                    "error_code": "unauthorized",
                }
            )
            return
        action = str(payload["action"])
        if action == "submit" and set(payload) == {"token", "action", "target"}:
            result = self.server.runtime.submit(str(payload["target"]))
        elif action == "status" and set(payload) == {"token", "action", "task_id"}:
            result = self.server.runtime.status(str(payload["task_id"]))
        elif action == "list" and set(payload) == {"token", "action"}:
            result = self.server.runtime.list_tasks()
        else:
            result = {
                "ok": False,
                "error": "Unsupported action or fields",
                "error_code": "invalid",
            }
        self._send(result)

    def _send(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n"
        self.wfile.write(data)
        self.wfile.flush()


class ReconcileUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, path: str, runtime: ReconcileRuntime) -> None:
        self.runtime = runtime
        super().__init__(path, ReconcileRequestHandler)


def _prepare_socket(path: Path, socket_gid: int) -> None:
    try:
        parent = path.parent.lstat()
    except FileNotFoundError as error:
        raise RuntimeError("Hermes reconcile runtime directory is missing") from error
    parent_mode = stat.S_IMODE(parent.st_mode)
    if (
        not stat.S_ISDIR(parent.st_mode)
        or parent.st_uid != 0
        or parent.st_gid != 0
        or parent_mode != 0o755
    ):
        raise RuntimeError(
            "Hermes reconcile runtime directory has unsafe type, owner, group or mode"
        )
    try:
        existing = path.lstat()
    except FileNotFoundError:
        return
    existing_mode = stat.S_IMODE(existing.st_mode)
    if (
        not stat.S_ISSOCK(existing.st_mode)
        or existing.st_uid != 0
        or existing.st_gid != socket_gid
        or existing_mode != 0o660
    ):
        raise RuntimeError("Refusing to replace unsafe Hermes reconcile socket")
    path.unlink()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    runtime_dir = Path(
        os.getenv(
            "HERMES_OPS_RECONCILE_RUNTIME_DIR",
            "/run/hermes-operator-reconcile",
        )
    ).resolve()
    socket_path = Path(
        os.getenv(
            "HERMES_OPS_RECONCILE_SOCKET",
            str(runtime_dir / "reconcile.sock"),
        )
    ).resolve()
    if socket_path.parent != runtime_dir:
        raise ConfigurationError(
            "HERMES_OPS_RECONCILE_SOCKET must be inside reconcile runtime dir"
        )
    socket_gid = int(os.getenv("HERMES_OPS_SOCKET_GID", "10001"))
    _prepare_socket(socket_path, socket_gid)
    server = ReconcileUnixServer(str(socket_path), ReconcileRuntime())
    os.chown(socket_path, 0, socket_gid)
    os.chmod(socket_path, 0o660)
    logger.info("Hermes reconcile bridge listening on %s", socket_path)
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
