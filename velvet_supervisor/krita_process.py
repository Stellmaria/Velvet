from __future__ import annotations

import csv
import json
import locale
import logging
import os
import shutil
import signal
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _parse_bool(value: str, *, default: bool) -> bool:
    cleaned = value.strip().casefold()
    if not cleaned:
        return default
    if cleaned in {"1", "true", "yes", "on", "да"}:
        return True
    if cleaned in {"0", "false", "no", "off", "нет"}:
        return False
    logger.warning("Invalid boolean value %r; using %s", value, default)
    return default


def _parse_int(value: str, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value.strip())
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _default_krita_executable() -> Path:
    configured = os.getenv("KRITA_EXECUTABLE", "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path(r"E:\Program Files\Krita (x64)\bin\krita.exe"),
        Path(r"C:\Program Files\Krita (x64)\bin\krita.exe"),
        Path(r"C:\Program Files\Krita\bin\krita.exe"),
        Path(os.getenv("LOCALAPPDATA", "")) / "Programs" / "Krita" / "bin" / "krita.exe",
    ]
    for candidate in candidates:
        if candidate is not None and str(candidate) and candidate.is_file():
            return candidate.resolve()
    if configured:
        return Path(configured).expanduser().resolve(strict=False)
    return Path(r"E:\Program Files\Krita (x64)\bin\krita.exe")


class KritaProcessManager:
    """Own one on-demand Krita process and stop only the process it started."""

    def __init__(self, *, project_dir: Path, runtime_dir: Path) -> None:
        self.project_dir = project_dir.resolve()
        self.runtime_dir = runtime_dir.resolve()
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

        watermark_enabled = _parse_bool(
            os.getenv("KRITA_WATERMARK_ENABLED", "false"),
            default=False,
        )
        self.enabled = _parse_bool(
            os.getenv("KRITA_AUTOSTART_ENABLED", ""),
            default=watermark_enabled,
        )
        self.executable = _default_krita_executable()
        self.bridge_dir = Path(
            os.getenv("KRITA_BRIDGE_DIR", str(Path.home() / "VelvetKritaBridge"))
        ).expanduser().resolve(strict=False)
        self.idle_timeout_seconds = _parse_int(
            os.getenv("KRITA_IDLE_TIMEOUT_SECONDS", "600"),
            default=600,
            minimum=60,
            maximum=86_400,
        )

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._monitor_thread: threading.Thread | None = None
        self._process: subprocess.Popen[Any] | None = None
        self._managed_pid: int | None = None
        self._external_pid: int | None = None
        self._last_used_monotonic: float | None = None
        self._last_used_at: datetime | None = None
        self._plugin_synced_at: datetime | None = None
        self._marker_path = self.runtime_dir / "krita-process.json"
        self._restore_marker()

    def start(self) -> None:
        if not self.enabled:
            return
        with self._lock:
            if self._monitor_thread is not None and self._monitor_thread.is_alive():
                return
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                name="velvet-krita-idle-monitor",
                daemon=True,
            )
            self._monitor_thread.start()

    def shutdown(self) -> None:
        self._stop_event.set()
        thread = self._monitor_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=3)
        # Do not terminate Krita during a Supervisor self-restart. The marker lets
        # the next Supervisor process reclaim ownership and continue the idle timer.

    def ensure(self) -> dict[str, Any]:
        if not self.enabled:
            raise RuntimeError(
                "Автозапуск Krita выключен. Установите KRITA_AUTOSTART_ENABLED=true."
            )

        with self._lock:
            running_pids = self._running_krita_pids()
            if self._managed_pid is not None and self._managed_pid in running_pids:
                self._touch_locked()
                return self._status_locked(running_pids)

            if self._managed_pid is not None:
                self._clear_managed_locked()

            if running_pids:
                self._external_pid = min(running_pids)
                self._touch_locked(write_marker=False)
                return self._status_locked(running_pids)

            if not self.executable.is_file():
                raise RuntimeError(f"Krita не найдена: {self.executable}")

            self._sync_plugin_locked()
            process = subprocess.Popen(
                [str(self.executable)],
                cwd=str(self.executable.parent),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            self._process = process
            self._managed_pid = int(process.pid)
            self._external_pid = None
            self._touch_locked()
            logger.info("Krita started on demand pid=%s", process.pid)
            return self._status_locked({int(process.pid)})

    def touch(self) -> dict[str, Any]:
        return self.ensure()

    def stop(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            running_pids = self._running_krita_pids()
            pid = self._managed_pid
            if pid is None or pid not in running_pids:
                self._clear_managed_locked()
                payload = self._status_locked(running_pids)
                payload["stopped"] = False
                return payload

            if self._bridge_busy() and not force:
                payload = self._status_locked(running_pids)
                payload["stopped"] = False
                payload["deferred"] = True
                return payload

            self._terminate_managed_locked(pid)
            payload = self._status_locked(self._running_krita_pids())
            payload["stopped"] = True
            logger.info("Managed Krita stopped pid=%s", pid)
            return payload

    def status(self) -> dict[str, Any]:
        with self._lock:
            return self._status_locked(self._running_krita_pids())

    def _status_locked(self, running_pids: set[int]) -> dict[str, Any]:
        if self._managed_pid is not None and self._managed_pid not in running_pids:
            self._clear_managed_locked()
        managed = self._managed_pid is not None and self._managed_pid in running_pids
        pid = self._managed_pid if managed else (min(running_pids) if running_pids else None)
        if not managed:
            self._external_pid = pid
        idle_seconds = None
        if self._last_used_monotonic is not None:
            idle_seconds = max(0.0, time.monotonic() - self._last_used_monotonic)
        return {
            "enabled": self.enabled,
            "running": bool(running_pids),
            "pid": pid,
            "managed": managed,
            "executable": str(self.executable),
            "bridge_dir": str(self.bridge_dir),
            "bridge_busy": self._bridge_busy(),
            "last_used_at": self._last_used_at.isoformat() if self._last_used_at else None,
            "idle_seconds": round(idle_seconds, 1) if idle_seconds is not None else None,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "plugin_synced_at": (
                self._plugin_synced_at.isoformat() if self._plugin_synced_at else None
            ),
        }

    def _monitor_loop(self) -> None:
        while not self._stop_event.wait(2.0):
            try:
                with self._lock:
                    running_pids = self._running_krita_pids()
                    pid = self._managed_pid
                    if pid is None or pid not in running_pids:
                        if pid is not None:
                            self._clear_managed_locked()
                        continue
                    if self._last_used_monotonic is None:
                        self._touch_locked()
                        continue
                    idle = time.monotonic() - self._last_used_monotonic
                    should_stop = (
                        idle >= self.idle_timeout_seconds and not self._bridge_busy()
                    )
                if should_stop:
                    self.stop()
            except Exception:
                logger.exception("Krita idle monitor iteration failed")

    def _touch_locked(self, *, write_marker: bool = True) -> None:
        self._last_used_monotonic = time.monotonic()
        self._last_used_at = datetime.now(UTC)
        if write_marker and self._managed_pid is not None:
            self._write_marker_locked()

    def _bridge_busy(self) -> bool:
        requests = self.bridge_dir / "requests"
        try:
            return any(requests.glob("*.json")) or any(requests.glob("*.processing"))
        except OSError:
            return False

    def _sync_plugin_locked(self) -> None:
        source_desktop = self.project_dir / "tools" / "krita" / "velvet_logo.desktop"
        source_plugin = self.project_dir / "tools" / "krita" / "velvet_logo"
        if not source_desktop.is_file() or not source_plugin.is_dir():
            logger.warning("Krita plugin source is missing under %s", self.project_dir)
            return

        configured = os.getenv("KRITA_PLUGIN_DIR", "").strip()
        if configured:
            destination = Path(configured).expanduser()
        else:
            appdata = os.getenv("APPDATA", "").strip()
            destination = (
                Path(appdata) / "krita" / "pykrita"
                if appdata
                else Path.home() / "AppData" / "Roaming" / "krita" / "pykrita"
            )
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_desktop, destination / source_desktop.name)
        shutil.copytree(
            source_plugin,
            destination / source_plugin.name,
            dirs_exist_ok=True,
        )
        self._plugin_synced_at = datetime.now(UTC)
        logger.info("Krita plugin synchronized to %s", destination)

    def _running_krita_pids(self) -> set[int]:
        if os.name != "nt":
            process = self._process
            if process is not None and process.poll() is None:
                return {int(process.pid)}
            return set()

        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            completed = subprocess.run(
                [
                    "tasklist.exe",
                    "/FI",
                    "IMAGENAME eq krita.exe",
                    "/FO",
                    "CSV",
                    "/NH",
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding=locale.getpreferredencoding(False),
                errors="replace",
                timeout=10,
                check=False,
                creationflags=creationflags,
            )
        except (OSError, subprocess.TimeoutExpired):
            process = self._process
            if process is not None and process.poll() is None:
                return {int(process.pid)}
            return set()

        pids: set[int] = set()
        for row in csv.reader(completed.stdout.splitlines()):
            if len(row) < 2 or row[0].strip().casefold() != "krita.exe":
                continue
            try:
                pids.add(int(row[1].replace(",", "").strip()))
            except ValueError:
                continue
        return pids

    def _terminate_managed_locked(self, pid: int) -> None:
        process = self._process
        if process is not None and int(process.pid) == pid and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        elif os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            subprocess.run(
                ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
                creationflags=creationflags,
            )
        else:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        self._clear_managed_locked()

    def _write_marker_locked(self) -> None:
        if self._managed_pid is None:
            return
        payload = {
            "pid": self._managed_pid,
            "executable": str(self.executable),
            "last_used_epoch": time.time(),
        }
        temporary = self._marker_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary.replace(self._marker_path)

    def _restore_marker(self) -> None:
        try:
            payload = json.loads(self._marker_path.read_text(encoding="utf-8"))
            pid = int(payload.get("pid", 0))
            last_used_epoch = float(payload.get("last_used_epoch", time.time()))
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            return
        if pid <= 0:
            return
        self._managed_pid = pid
        idle = max(0.0, time.time() - last_used_epoch)
        self._last_used_monotonic = time.monotonic() - idle
        self._last_used_at = datetime.fromtimestamp(last_used_epoch, tz=UTC)

    def _clear_managed_locked(self) -> None:
        self._process = None
        self._managed_pid = None
        self._marker_path.unlink(missing_ok=True)


__all__ = ("KritaProcessManager",)
