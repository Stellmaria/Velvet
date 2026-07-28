from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path


class SupervisorAlreadyRunning(RuntimeError):
    """Raised when another live Supervisor owns the runtime directory."""


@dataclass(slots=True)
class SupervisorInstanceGuard:
    path: Path
    pid: int = field(default_factory=os.getpid)
    _acquired: bool = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": int(self.pid),
            "created_at": time.time(),
        }
        for _attempt in range(2):
            try:
                with self.path.open("x", encoding="utf-8") as stream:
                    json.dump(payload, stream, ensure_ascii=False)
                self._acquired = True
                return
            except FileExistsError:
                owner_pid = self._read_owner_pid()
                if owner_pid and _pid_is_alive(owner_pid):
                    raise SupervisorAlreadyRunning(
                        f"Velvet Supervisor уже запущен (PID {owner_pid})."
                    )
                self.path.unlink(missing_ok=True)
        raise SupervisorAlreadyRunning(
            "Не удалось получить блокировку Velvet Supervisor."
        )

    def release(self) -> None:
        if not self._acquired:
            return
        try:
            owner_pid = self._read_owner_pid()
            if owner_pid == self.pid:
                self.path.unlink(missing_ok=True)
        finally:
            self._acquired = False

    def _read_owner_pid(self) -> int | None:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            value = int(payload.get("pid", 0))
        except (FileNotFoundError, OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        return value if value > 0 else None

    def __enter__(self) -> "SupervisorInstanceGuard":
        self.acquire()
        return self

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.release()


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


__all__ = (
    "SupervisorAlreadyRunning",
    "SupervisorInstanceGuard",
)
