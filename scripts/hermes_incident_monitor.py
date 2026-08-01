from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from velvet_supervisor.hermes_incident import (  # noqa: E402
    HermesIncident,
    HermesIncidentClient,
    redact_sensitive,
)
from velvet_supervisor.notifier import TelegramNotifier  # noqa: E402

logger = logging.getLogger("velvet.hermes_incident_monitor")
_ACTIVE_INCIDENT_STATES = frozenset({"queued", "submitted", "running"})


def _parse_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().casefold()
    if raw in {"1", "true", "yes", "on", "да"}:
        return True
    if raw in {"0", "false", "no", "off", "нет"}:
        return False
    raise RuntimeError(f"{name} must be boolean.")


def _parse_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer.") from error
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}.")
    return value


def _optional_chat_id() -> int | None:
    direct = os.getenv(
        "SUPERVISOR_NOTIFICATION_CHAT_ID",
        os.getenv("LOG_CHAT_ID", ""),
    ).strip()
    candidates = [direct] if direct else []
    owners = os.getenv(
        "SUPERVISOR_NOTIFICATION_OWNER_IDS",
        os.getenv(
            "ALLOWED_USER_IDS",
            os.getenv("TELEGRAM_ALLOWED_USERS", ""),
        ),
    )
    candidates.extend(item.strip() for item in owners.split(",") if item.strip())
    for raw in candidates:
        try:
            return int(raw)
        except ValueError:
            logger.warning("Invalid incident notification chat id: %r", raw)
    return None


@dataclass(frozen=True, slots=True)
class BotProbe:
    container_id: str | None
    running: bool
    status: str | None
    health: str | None
    restart_count: int
    exit_code: int | None
    error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "container_id": self.container_id,
            "running": self.running,
            "status": self.status,
            "health": self.health,
            "restart_count": self.restart_count,
            "exit_code": self.exit_code,
            "error": self.error,
        }


class HermesIncidentMonitor:
    """Read-only Docker monitor that escalates bounded incidents to main Hermes."""

    def __init__(self) -> None:
        self.enabled = _parse_bool("HERMES_INCIDENT_ENABLED", False)
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
        self.state_path = self.runtime_dir / "hermes-incident-monitor.json"
        self.log_path = self.data_dir / "logs" / "hermes-incident-monitor.log"
        self.poll_seconds = _parse_int(
            "HERMES_INCIDENT_POLL_SECONDS",
            30,
            minimum=5,
            maximum=3600,
        )
        self.unhealthy_threshold = _parse_int(
            "HERMES_INCIDENT_UNHEALTHY_POLLS",
            2,
            minimum=1,
            maximum=20,
        )
        self.log_lines = _parse_int(
            "HERMES_INCIDENT_LOG_LINES",
            200,
            minimum=20,
            maximum=2000,
        )
        self.event_cooldown_seconds = _parse_int(
            "HERMES_INCIDENT_COOLDOWN_SECONDS",
            600,
            minimum=30,
            maximum=86_400,
        )
        self._stop = threading.Event()
        self._state = self._load_state()
        self._unhealthy_polls = 0
        self._last_event_key = str(self._state.get("last_event_key") or "")
        try:
            self._last_event_at = float(self._state.get("last_event_at") or 0.0)
        except (TypeError, ValueError):
            self._last_event_at = 0.0
        self.notifier = TelegramNotifier(
            bot_token=(
                os.getenv("SUPERVISOR_NOTIFICATION_BOT_TOKEN", "").strip()
                or os.getenv("BOT_TOKEN", "").strip()
                or None
            ),
            chat_id=_optional_chat_id(),
        )
        self.client = HermesIncidentClient(
            enabled=self.enabled,
            base_url=os.getenv(
                "HERMES_BASE_URL",
                "http://127.0.0.1:8642",
            ),
            api_key=os.getenv("HERMES_API_KEY", "").strip() or None,
            timeout_seconds=_parse_int(
                "HERMES_TIMEOUT_SECONDS",
                20,
                minimum=3,
                maximum=300,
            ),
            cooldown_seconds=self.event_cooldown_seconds,
            max_log_chars=_parse_int(
                "HERMES_MAX_LOG_CHARS",
                12_000,
                minimum=1000,
                maximum=200_000,
            ),
            poll_interval_seconds=float(
                _parse_int(
                    "HERMES_INCIDENT_RUN_POLL_SECONDS",
                    5,
                    minimum=1,
                    maximum=60,
                )
            ),
            run_timeout_seconds=_parse_int(
                "HERMES_INCIDENT_RUN_TIMEOUT_SECONDS",
                3600,
                minimum=60,
                maximum=14_400,
            ),
            result_callback=self._on_result,
        )
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def stop(self) -> None:
        self._stop.set()

    def _compose(self, *args: str) -> list[str]:
        return [
            "docker",
            "compose",
            "--env-file",
            self.env_file,
            "-f",
            self.compose_file,
            *args,
        ]

    def _run(self, command: list[str], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=self.app_dir,
            env=os.environ.copy(),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )

    def probe(self) -> BotProbe:
        container = self._run(self._compose("ps", "-q", "bot"), timeout=30)
        container_id = container.stdout.strip()
        if container.returncode != 0:
            return BotProbe(
                container_id=None,
                running=False,
                status=None,
                health=None,
                restart_count=0,
                exit_code=None,
                error="Compose bot lookup failed.",
            )
        if not container_id:
            return BotProbe(
                container_id=None,
                running=False,
                status="missing",
                health=None,
                restart_count=0,
                exit_code=None,
                error=None,
            )
        inspected = self._run(["docker", "inspect", container_id], timeout=30)
        if inspected.returncode != 0:
            return BotProbe(
                container_id=container_id,
                running=False,
                status=None,
                health=None,
                restart_count=0,
                exit_code=None,
                error="Docker inspect failed.",
            )
        try:
            payload = json.loads(inspected.stdout)[0]
            state = payload.get("State", {})
            health = state.get("Health") or {}
            return BotProbe(
                container_id=container_id,
                running=bool(state.get("Running")),
                status=str(state.get("Status") or "") or None,
                health=str(health.get("Status") or "") or None,
                restart_count=max(0, int(payload.get("RestartCount", 0) or 0)),
                exit_code=(
                    int(state.get("ExitCode"))
                    if state.get("ExitCode") is not None
                    else None
                ),
                error=None,
            )
        except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError):
            logger.exception("Could not parse Docker inspect output")
            return BotProbe(
                container_id=container_id,
                running=False,
                status=None,
                health=None,
                restart_count=0,
                exit_code=None,
                error="Docker inspect payload is invalid.",
            )

    def _load_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_state(self, probe: BotProbe) -> None:
        payload = {
            "updated_at": time.time(),
            "probe": probe.to_dict(),
            "incident": self.client.status(),
            "last_event_key": self._last_event_key,
            "last_event_at": self._last_event_at,
        }
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        temporary.replace(self.state_path)
        os.chmod(self.state_path, 0o600)
        self._state = payload

    def _previous_probe(self) -> dict[str, Any]:
        value = self._state.get("probe")
        return value if isinstance(value, dict) else {}

    def _reason(self, probe: BotProbe) -> str | None:
        previous = self._previous_probe()
        if not previous:
            if not probe.running or probe.health == "unhealthy":
                return "initial-unhealthy-state"
            return None
        previous_restarts = max(0, int(previous.get("restart_count", 0) or 0))
        if probe.restart_count > previous_restarts:
            return "container-auto-restarted"
        if not probe.running:
            return "container-not-running"
        if probe.health == "unhealthy":
            self._unhealthy_polls += 1
            if self._unhealthy_polls >= self.unhealthy_threshold:
                return "container-unhealthy"
        else:
            self._unhealthy_polls = 0
        return None

    @staticmethod
    def _event_key(probe: BotProbe, reason: str) -> str:
        return "|".join(
            (
                reason,
                probe.container_id or "missing",
                str(probe.restart_count),
                probe.status or "unknown",
                probe.health or "none",
            )
        )

    def _can_submit(self, event_key: str) -> bool:
        if str(self.client.status().get("state")) in _ACTIVE_INCIDENT_STATES:
            return False
        if event_key != self._last_event_key:
            return True
        return time.time() - self._last_event_at >= self.event_cooldown_seconds

    def _logs(self) -> str:
        result = self._run(
            self._compose(
                "logs",
                "--no-color",
                "--tail",
                str(self.log_lines),
                "bot",
            ),
            timeout=60,
        )
        return redact_sensitive(result.stdout)[-200_000:]

    def _git(self, *args: str) -> str | None:
        result = self._run(["git", *args], timeout=30)
        value = result.stdout.strip()
        return value if result.returncode == 0 and value else None

    def _submit(self, probe: BotProbe, reason: str) -> None:
        event_key = self._event_key(probe, reason)
        if not self._can_submit(event_key):
            return
        incident = HermesIncident(
            service="velvet-bot",
            reason=reason,
            exit_code=probe.exit_code,
            restart_count=probe.restart_count,
            crash_loop_open=(not probe.running or probe.health == "unhealthy"),
            log_tail=self._logs(),
            git_head=self._git("rev-parse", "HEAD"),
            branch=self._git("branch", "--show-current"),
        )
        if self.client.submit_async(incident):
            self._last_event_key = event_key
            self._last_event_at = time.time()
            logger.warning(
                "Submitted server incident reason=%s restarts=%s health=%s",
                reason,
                probe.restart_count,
                probe.health,
            )
            self.notifier.send(
                "Hermes начал разбор серверного инцидента",
                (
                    f"reason={reason}\n"
                    f"running={probe.running}\n"
                    f"health={probe.health}\n"
                    f"restart_count={probe.restart_count}"
                ),
                level="ERROR",
            )

    def _on_result(self, report: dict[str, Any]) -> None:
        status = str(report.get("status") or "unknown")
        output = redact_sensitive(str(report.get("output") or "[empty]"))[-3000:]
        self.notifier.send(
            "Hermes завершил разбор серверного инцидента",
            (
                f"run_id={report.get('run_id') or 'unknown'}\n"
                f"status={status}\n\n{output}"
            ),
            level="INFO" if status == "completed" else "ERROR",
        )

    def run(self) -> int:
        if not self.enabled:
            logger.warning("Hermes incident monitor is installed but disabled")
        while not self._stop.is_set():
            try:
                probe = self.probe()
                if self.enabled:
                    reason = self._reason(probe)
                    if reason is not None:
                        self._submit(probe, reason)
                self._save_state(probe)
            except Exception:
                logger.exception("Hermes incident monitor poll failed")
            self._stop.wait(self.poll_seconds)
        return 0


def main() -> int:
    monitor = HermesIncidentMonitor()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(monitor.log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )

    def stop(_signum: int, _frame: Any) -> None:
        monitor.stop()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    logger.info(
        "Hermes incident monitor started enabled=%s interval=%ss",
        monitor.enabled,
        monitor.poll_seconds,
    )
    return monitor.run()


if __name__ == "__main__":
    raise SystemExit(main())
