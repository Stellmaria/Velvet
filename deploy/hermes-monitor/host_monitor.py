from __future__ import annotations

import hmac
import json
import logging
import os
import re
import shutil
import socketserver
import stat
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("velvet.hermes_monitor_host")
_MAX_REQUEST_BYTES = 4096
_MAX_OUTPUT_BYTES = 262144
_ALLOWED_VIEWS = frozenset({"summary", "resources", "containers", "services", "gpu", "models", "processes", "incidents"})
_FIXED_UNITS = (
    "docker.service", "velvet-compose.service", "romatic-compose.service",
    "velvet-server-supervisor.service", "romatic-server-supervisor.service",
    "hermes-operator-host.service", "hermes-operator-control.service",
    "hermes-operator-reconcile.service", "hermes-reconcile-gateway.service",
    "hermes-operator-monitor.service", "hermes-monitor-gateway.service",
    "hermes-coders.service", "hermes-coder-router.service",
    "velvet-librarian.service", "velvet-hermes-incident-monitor.service",
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bauthorization\b\s*:\s*bearer\s+[^\s,;]+"),
    re.compile(r"(?i)\b(bearer|token|api[_-]?key|secret|password)\b\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)(https?://[^\s/:]+:)[^@\s]+@"),
    re.compile(r"\b(?:ghp|github_pat|sk|xox[baprs])_[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\b[A-Za-z0-9_-]{40,}\b"),
)


class ConfigurationError(RuntimeError):
    pass


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} must be configured")
    return value


def _bounded(value: str, limit: int = 500) -> str:
    return " ".join(value.replace("\x00", " ").split())[:limit]


def _redact(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        result = pattern.sub(
            lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]",
            result,
        )
    return _bounded(result)


def _read_meminfo(path: Path = Path("/proc/meminfo")) -> dict[str, int]:
    result: dict[str, int] = {}
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        parts = value.strip().split()
        if parts and parts[0].isdigit():
            amount = int(parts[0])
            result[key] = amount * 1024 if len(parts) > 1 and parts[1].lower() == "kb" else amount
    return result


def _key_values(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in text.splitlines():
        if "=" in raw:
            key, value = raw.split("=", 1)
            result[key.strip()] = value.strip()
    return result


class MonitorRuntime:
    def __init__(self) -> None:
        self.token = _required("HERMES_OPS_MONITOR_TOKEN")
        if len(self.token) < 24:
            raise ConfigurationError("HERMES_OPS_MONITOR_TOKEN must contain at least 24 characters")
        self.timeout = max(2, min(int(os.getenv("HERMES_OPS_MONITOR_TIMEOUT_SECONDS", "12")), 30))

    def _run(self, command: list[str], timeout: int | None = None) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            env={"PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout or self.timeout,
            check=False,
        )
        completed.stdout = completed.stdout[:_MAX_OUTPUT_BYTES]
        return completed

    def collect(self, view: str) -> dict[str, Any]:
        handlers: dict[str, Callable[[], dict[str, Any]]] = {
            "summary": self.summary, "resources": self.resources, "containers": self.containers,
            "services": self.services, "gpu": self.gpu, "models": self.models,
            "processes": self.processes, "incidents": self.incidents,
        }
        handler = handlers.get(view)
        if handler is None:
            return {"ok": False, "error": "Unknown monitor view", "error_code": "unknown_view"}
        result = handler()
        result.update({"ok": True, "view": view, "observed_at": int(time.time())})
        return result

    def resources(self) -> dict[str, Any]:
        mem = _read_meminfo()
        total, available = mem.get("MemTotal", 0), mem.get("MemAvailable", 0)
        swap_total, swap_free = mem.get("SwapTotal", 0), mem.get("SwapFree", 0)
        disk, fs = shutil.disk_usage("/"), os.statvfs("/")
        try:
            uptime = float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])
        except (OSError, ValueError, IndexError):
            uptime = None
        return {
            "hostname": os.uname().nodename, "uptime_seconds": uptime,
            "load_average": list(os.getloadavg()), "cpu_count": os.cpu_count(),
            "memory": {"total_bytes": total, "available_bytes": available, "used_bytes": max(0, total - available), "used_percent": round((total - available) * 100 / total, 2) if total else None},
            "swap": {"total_bytes": swap_total, "used_bytes": max(0, swap_total - swap_free), "used_percent": round((swap_total - swap_free) * 100 / swap_total, 2) if swap_total else 0.0},
            "disk_root": {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free, "used_percent": round(disk.used * 100 / disk.total, 2) if disk.total else None, "inode_total": fs.f_files, "inode_free": fs.f_ffree, "inode_used_percent": round((fs.f_files - fs.f_ffree) * 100 / fs.f_files, 2) if fs.f_files else None},
        }

    def containers(self) -> dict[str, Any]:
        if shutil.which("docker") is None:
            return {"available": False, "reason": "docker command is unavailable", "items": []}
        listed = self._run(["docker", "ps", "-a", "--no-trunc", "--format", "{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.State}}\t{{.Status}}"])
        if listed.returncode:
            return {"available": False, "reason": _redact(listed.stdout), "items": []}
        rows = [parts for raw in listed.stdout.splitlines()[:100] if len(parts := raw.split("\t", 4)) == 5]
        details: dict[str, tuple[dict[str, Any], int]] = {}
        ids = [row[0] for row in rows]
        if ids:
            inspected = self._run(["docker", "inspect", "--format", "{{.Id}}\t{{json .State}}\t{{.RestartCount}}", *ids], timeout=20)
            if not inspected.returncode:
                for raw in inspected.stdout.splitlines():
                    parts = raw.split("\t", 2)
                    if len(parts) != 3:
                        continue
                    try:
                        state = json.loads(parts[1])
                        details[parts[0]] = (state if isinstance(state, dict) else {}, int(parts[2] or 0))
                    except (json.JSONDecodeError, ValueError):
                        continue
        items = []
        for container_id, name, image, state_text, status_text in rows:
            state, restarts = details.get(container_id, ({}, 0))
            health = state.get("Health")
            items.append({
                "id": container_id[:12], "name": _bounded(name, 128), "image": _bounded(image, 256),
                "state": state_text, "status": _bounded(status_text, 256), "running": bool(state.get("Running")),
                "health": health.get("Status") if isinstance(health, dict) else None, "restart_count": restarts,
                "started_at": state.get("StartedAt"), "finished_at": state.get("FinishedAt"),
                "exit_code": state.get("ExitCode"), "oom_killed": bool(state.get("OOMKilled")),
            })
        return {"available": True, "count": len(items), "running": sum(bool(item["running"]) for item in items), "unhealthy": sum(item["health"] == "unhealthy" for item in items), "items": items}

    def services(self) -> dict[str, Any]:
        if shutil.which("systemctl") is None:
            return {"available": False, "reason": "systemctl is unavailable", "items": []}
        items = []
        for unit in _FIXED_UNITS:
            completed = self._run(["systemctl", "show", unit, "--no-pager", "--property=LoadState,ActiveState,SubState,UnitFileState,Result,NRestarts,ExecMainStatus,ActiveEnterTimestamp"], timeout=5)
            values = _key_values(completed.stdout)
            items.append({
                "unit": unit, "load_state": values.get("LoadState", "unknown"),
                "active_state": values.get("ActiveState", "unknown"), "sub_state": values.get("SubState", "unknown"),
                "unit_file_state": values.get("UnitFileState", "unknown"), "result": values.get("Result") or None,
                "restart_count": int(values.get("NRestarts", "0") or 0), "exec_main_status": int(values.get("ExecMainStatus", "0") or 0),
                "active_since": values.get("ActiveEnterTimestamp") or None,
                "error": _redact(completed.stdout) if completed.returncode and not values else None,
            })
        return {"available": True, "count": len(items), "failed": sum(item["load_state"] == "loaded" and item["active_state"] == "failed" for item in items), "items": items}

    def gpu(self) -> dict[str, Any]:
        if shutil.which("nvidia-smi") is None:
            return {"available": False, "reason": "nvidia-smi is unavailable", "items": []}
        completed = self._run(["nvidia-smi", "--query-gpu=index,name,uuid,temperature.gpu,utilization.gpu,memory.total,memory.used,memory.free,power.draw", "--format=csv,noheader,nounits"], timeout=8)
        if completed.returncode:
            return {"available": False, "reason": _redact(completed.stdout), "items": []}
        keys = ("index", "name", "uuid", "temperature_c", "utilization_percent", "memory_total_mib", "memory_used_mib", "memory_free_mib", "power_draw_w")
        items = [dict(zip(keys, [part.strip() for part in raw.split(",")], strict=True)) for raw in completed.stdout.splitlines()[:16] if len(raw.split(",")) == len(keys)]
        return {"available": True, "count": len(items), "items": items}

    def models(self) -> dict[str, Any]:
        result: dict[str, Any] = {"host_ollama_available": False, "running": [], "installed": [], "ollama_containers": []}
        if shutil.which("ollama") is not None:
            result["host_ollama_available"] = True
            for command, key in ((["ollama", "ps"], "running"), (["ollama", "list"], "installed")):
                completed = self._run(command, timeout=8)
                result[key] = [_bounded(line, 300) for line in completed.stdout.splitlines()[:50]] if not completed.returncode else []
                if completed.returncode:
                    result[f"{key}_error"] = _redact(completed.stdout)
        containers = self.containers()
        result["ollama_containers"] = [item for item in containers.get("items", []) if "ollama" in f"{item.get('name', '')} {item.get('image', '')}".lower()]
        result["available"] = bool(result["host_ollama_available"] or result["ollama_containers"])
        return result

    def processes(self) -> dict[str, Any]:
        if shutil.which("ps") is None:
            return {"available": False, "reason": "ps is unavailable", "items": []}
        completed = self._run(["ps", "-eo", "pid=,user=,comm=,%cpu=,%mem=,etimes=,stat=", "--sort=-%cpu"])
        if completed.returncode:
            return {"available": False, "reason": _redact(completed.stdout), "items": []}
        items = []
        for raw in completed.stdout.splitlines()[:30]:
            parts = raw.split(None, 6)
            if len(parts) == 7 and parts[0].isdigit():
                items.append({"pid": int(parts[0]), "user": _bounded(parts[1], 64), "command": _bounded(parts[2], 128), "cpu_percent": float(parts[3]), "memory_percent": float(parts[4]), "elapsed_seconds": int(parts[5]), "state": _bounded(parts[6], 32)})
        return {"available": True, "count": len(items), "items": items}

    def incidents(self) -> dict[str, Any]:
        if shutil.which("journalctl") is None:
            return {"available": False, "reason": "journalctl is unavailable", "items": []}
        completed = self._run(["journalctl", "--priority=warning..alert", "--since=-30min", "--no-pager", "--output=json", "--output-fields=__REALTIME_TIMESTAMP,_SYSTEMD_UNIT,PRIORITY,MESSAGE", "--lines=100"], timeout=12)
        if completed.returncode:
            return {"available": False, "reason": _redact(completed.stdout), "items": []}
        items = []
        for raw in completed.stdout.splitlines()[:100]:
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(entry, dict):
                items.append({"timestamp_us": entry.get("__REALTIME_TIMESTAMP"), "unit": _bounded(str(entry.get("_SYSTEMD_UNIT") or "kernel"), 128), "priority": str(entry.get("PRIORITY") or ""), "message": _redact(str(entry.get("MESSAGE") or ""))})
        return {"available": True, "count": len(items), "window_minutes": 30, "items": items}

    def summary(self) -> dict[str, Any]:
        resources, containers, services, gpu, models, incidents = self.resources(), self.containers(), self.services(), self.gpu(), self.models(), self.incidents()
        return {
            "resources": resources,
            "container_summary": {"available": containers.get("available"), "count": containers.get("count", 0), "running": containers.get("running", 0), "unhealthy": containers.get("unhealthy", 0)},
            "service_summary": {"available": services.get("available"), "count": services.get("count", 0), "failed": services.get("failed", 0)},
            "gpu_summary": {"available": gpu.get("available"), "count": gpu.get("count", 0)},
            "model_summary": {"available": models.get("available"), "running_lines": len(models.get("running", [])), "installed_lines": len(models.get("installed", [])), "ollama_containers": len(models.get("ollama_containers", []))},
            "incident_summary": {"available": incidents.get("available"), "count": incidents.get("count", 0), "window_minutes": incidents.get("window_minutes", 30)},
        }


class MonitorRequestHandler(socketserver.StreamRequestHandler):
    server: "MonitorUnixServer"

    def handle(self) -> None:
        raw = self.rfile.readline(_MAX_REQUEST_BYTES + 1)
        if not raw or len(raw) > _MAX_REQUEST_BYTES or not raw.endswith(b"\n"):
            self._send({"ok": False, "error": "Invalid request", "error_code": "invalid"})
            return
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._send({"ok": False, "error": "Invalid JSON", "error_code": "invalid"})
            return
        if not isinstance(payload, dict) or set(payload) != {"token", "view"}:
            self._send({"ok": False, "error": "Invalid fields", "error_code": "invalid"})
            return
        if not hmac.compare_digest(str(payload["token"]), self.server.runtime.token):
            self._send({"ok": False, "error": "Unauthorized", "error_code": "unauthorized"})
            return
        view = str(payload["view"])
        if view not in _ALLOWED_VIEWS:
            self._send({"ok": False, "error": "Unknown monitor view", "error_code": "unknown_view"})
            return
        try:
            result = self.server.runtime.collect(view)
        except Exception:
            logger.exception("Hermes monitor collection failed view=%s", view)
            result = {"ok": False, "error": "Monitor collection failed", "error_code": "collection_failed"}
        self._send(result)

    def _send(self, payload: dict[str, Any]) -> None:
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
        self.wfile.flush()


class MonitorUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True

    def __init__(self, path: str, runtime: MonitorRuntime) -> None:
        self.runtime = runtime
        super().__init__(path, MonitorRequestHandler)


def _prepare_socket(path: Path, socket_gid: int) -> None:
    try:
        parent = path.parent.lstat()
    except FileNotFoundError as error:
        raise RuntimeError("Hermes monitor runtime directory is missing") from error
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid != 0 or parent.st_gid != socket_gid or stat.S_IMODE(parent.st_mode) != 0o750:
        raise RuntimeError("Hermes monitor runtime directory has unsafe owner, group or mode")
    try:
        existing = path.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISSOCK(existing.st_mode) or existing.st_uid != 0 or existing.st_gid != socket_gid or stat.S_IMODE(existing.st_mode) != 0o660:
        raise RuntimeError("Refusing to replace unsafe Hermes monitor socket")
    path.unlink()


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    socket_path = Path(os.getenv("HERMES_OPS_MONITOR_SOCKET", "/run/hermes-operator-monitor/monitor.sock")).resolve()
    runtime_dir = Path(os.getenv("HERMES_OPS_MONITOR_RUNTIME_DIR", "/run/hermes-operator-monitor")).resolve()
    if socket_path.parent != runtime_dir:
        raise ConfigurationError("HERMES_OPS_MONITOR_SOCKET must be inside runtime dir")
    socket_gid = int(os.getenv("HERMES_OPS_SOCKET_GID", "10001"))
    _prepare_socket(socket_path, socket_gid)
    server = MonitorUnixServer(str(socket_path), MonitorRuntime())
    os.chown(socket_path, 0, socket_gid)
    os.chmod(socket_path, 0o660)
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
