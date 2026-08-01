from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

logger = logging.getLogger(__name__)
_TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})
_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|API_KEY)[A-Z0-9_]*\s*[=:]\s*)[^\s,;]+"),
    re.compile(r"(?i)(postgres(?:ql)?://[^:\s/]+:)[^@\s]+(@)"),
    re.compile(r"\b\d{8,12}:[A-Za-z0-9_-]{20,}\b"),
)


@dataclass(frozen=True, slots=True)
class HermesIncident:
    service: str
    reason: str
    exit_code: int | None
    restart_count: int
    crash_loop_open: bool
    log_tail: str
    git_head: str | None = None
    branch: str | None = None

    def fingerprint(self) -> str:
        seed = "|".join(
            (
                self.service.strip().casefold(),
                self.reason.strip().casefold(),
                str(self.exit_code),
                _last_error_signature(self.log_tail),
            )
        )
        return hashlib.sha256(seed.encode("utf-8", errors="replace")).hexdigest()


class HermesIncidentClient:
    """Submit bounded incidents, wait for Hermes and surface the terminal report."""

    def __init__(
        self,
        *,
        enabled: bool,
        base_url: str,
        api_key: str | None,
        timeout_seconds: int = 20,
        cooldown_seconds: int = 600,
        max_log_chars: int = 12_000,
        poll_interval_seconds: float = 5.0,
        run_timeout_seconds: int = 3600,
        result_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.enabled = bool(enabled)
        self.base_url = base_url.strip().rstrip("/")
        self.api_key = (api_key or "").strip() or None
        self.timeout_seconds = max(3, int(timeout_seconds))
        self.cooldown_seconds = max(30, int(cooldown_seconds))
        self.max_log_chars = max(1000, int(max_log_chars))
        self.poll_interval_seconds = max(0.5, float(poll_interval_seconds))
        self.run_timeout_seconds = max(60, int(run_timeout_seconds))
        self.result_callback = result_callback
        if self.enabled and not self.base_url:
            raise ValueError("Hermes base URL не может быть пустым.")
        if self.enabled and (self.api_key is None or len(self.api_key) < 8):
            raise ValueError("Hermes API key должен содержать минимум 8 символов.")

        self._lock = threading.Lock()
        self._last_submitted: dict[str, float] = {}
        self._last_status: dict[str, Any] = {
            "enabled": self.enabled,
            "state": "idle" if self.enabled else "disabled",
            "run_id": None,
            "run_status": None,
            "output": None,
            "error": None,
            "submitted_at": None,
            "finished_at": None,
            "fingerprint": None,
        }

    def submit_async(self, incident: HermesIncident) -> bool:
        if not self.enabled:
            return False
        fingerprint = incident.fingerprint()
        now = time.monotonic()
        with self._lock:
            previous = self._last_submitted.get(fingerprint)
            if previous is not None and now - previous < self.cooldown_seconds:
                self._last_status = {
                    **self._last_status,
                    "state": "cooldown",
                    "fingerprint": fingerprint,
                }
                return False
            self._last_submitted[fingerprint] = now
            self._last_status = {
                "enabled": True,
                "state": "queued",
                "run_id": None,
                "run_status": None,
                "output": None,
                "error": None,
                "submitted_at": _utc_iso(),
                "finished_at": None,
                "fingerprint": fingerprint,
            }

        thread = threading.Thread(
            target=self._submit_worker,
            args=(incident, fingerprint),
            name=f"hermes-incident:{fingerprint[:12]}",
            daemon=True,
        )
        thread.start()
        return True

    def submit(self, incident: HermesIncident) -> str:
        if not self.enabled:
            raise RuntimeError("Hermes incident integration выключена.")
        payload = self._request_json(
            "POST",
            "/v1/runs",
            self._request_body(incident),
        )
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id.strip():
            raise RuntimeError(f"Hermes не вернул run_id: {payload!r}")
        return run_id.strip()

    def wait_for_run(self, run_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.run_timeout_seconds
        while True:
            payload = self._request_json("GET", f"/v1/runs/{run_id}")
            status = str(payload.get("status", "unknown"))
            with self._lock:
                self._last_status = {
                    **self._last_status,
                    "state": "running" if status not in _TERMINAL_RUN_STATUSES else "finished",
                    "run_id": run_id,
                    "run_status": status,
                    "output": redact_sensitive(str(payload.get("output") or ""))[:12_000] or None,
                }
            if status in _TERMINAL_RUN_STATUSES:
                return payload
            if time.monotonic() >= deadline:
                raise RuntimeError(
                    f"Hermes run {run_id} не завершился за {self.run_timeout_seconds} секунд."
                )
            time.sleep(self.poll_interval_seconds)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last_status)

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        assert self.api_key is not None
        data = None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json",
        }
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")[:1000]
            raise RuntimeError(f"Hermes HTTP {error.code}: {redact_sensitive(details)}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RuntimeError(f"Hermes недоступен: {error}") from error
        try:
            result = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RuntimeError("Hermes вернул повреждённый JSON.") from error
        if not isinstance(result, dict):
            raise RuntimeError("Hermes вернул неожиданный ответ.")
        return result

    def _submit_worker(self, incident: HermesIncident, fingerprint: str) -> None:
        try:
            run_id = self.submit(incident)
            with self._lock:
                self._last_status = {
                    **self._last_status,
                    "state": "submitted",
                    "run_id": run_id,
                    "run_status": "started",
                }
            result = self.wait_for_run(run_id)
            run_status = str(result.get("status", "unknown"))
            output = redact_sensitive(
                str(result.get("output") or result.get("error") or "")
            )[:12_000]
            report = {
                "run_id": run_id,
                "status": run_status,
                "output": output,
                "fingerprint": fingerprint,
                "finished_at": _utc_iso(),
            }
            with self._lock:
                self._last_status = {
                    **self._last_status,
                    "state": "finished",
                    "run_id": run_id,
                    "run_status": run_status,
                    "output": output or None,
                    "error": None,
                    "finished_at": report["finished_at"],
                }
            if self.result_callback is not None:
                try:
                    self.result_callback(report)
                except Exception:
                    logger.exception("Hermes incident result callback failed")
        except Exception as error:
            safe_error = redact_sensitive(str(error))[:2000]
            with self._lock:
                self._last_status = {
                    **self._last_status,
                    "state": "error",
                    "run_status": "failed",
                    "error": safe_error,
                    "finished_at": _utc_iso(),
                    "fingerprint": fingerprint,
                }
            if self.result_callback is not None:
                try:
                    self.result_callback(
                        {
                            "run_id": self._last_status.get("run_id"),
                            "status": "failed",
                            "output": safe_error,
                            "fingerprint": fingerprint,
                            "finished_at": self._last_status["finished_at"],
                        }
                    )
                except Exception:
                    logger.exception("Hermes incident error callback failed")

    def _request_body(self, incident: HermesIncident) -> dict[str, Any]:
        sanitized_logs = redact_sensitive(incident.log_tail)[-self.max_log_chars :]
        sanitized_reason = redact_sensitive(incident.reason)[:2000]
        prompt = (
            "Разбери аварийный инцидент Velvet. Не выполняй опасные действия и не "
            "запрашивай секреты. Сначала классифицируй причину и проверь безопасную "
            "диагностику. Если это вероятный дефект кода, поставь изолированному Velvet "
            "coder задачу через `python /opt/data/tools/coderctl.py submit velvet "
            "--source automatic-incident --task <очищенная задача>`, дождись результата "
            "через coderctl wait и проверь созданный PR и CI. Не выполняй merge, update, "
            "restart, rollback или изменение production. Если данных недостаточно, не "
            "создавай задачу и явно укажи, что требуется от владельца.\n\n"
            f"service: {incident.service}\n"
            f"reason: {sanitized_reason}\n"
            f"exit_code: {incident.exit_code}\n"
            f"restart_count: {incident.restart_count}\n"
            f"crash_loop_open: {incident.crash_loop_open}\n"
            f"branch: {incident.branch or 'unknown'}\n"
            f"git_head: {incident.git_head or 'unknown'}\n\n"
            "Последние очищенные логи:\n"
            f"{sanitized_logs or '[empty]'}"
        )
        return {
            "input": prompt,
            "session_id": f"velvet-incident-{incident.fingerprint()[:16]}",
            "instructions": (
                "Ты главный аварийный оператор Velvet. Верни краткий диагноз, риск, "
                "task_id/run_id coder-задачи, PR и тесты либо точный blocker. Итог будет "
                "автоматически отправлен владельцу в Telegram."
            ),
        }


def redact_sensitive(value: str) -> str:
    result = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups >= 2:
            result = pattern.sub(r"\1[REDACTED]\2", result)
        elif pattern.groups == 1:
            result = pattern.sub(r"\1[REDACTED]", result)
        else:
            result = pattern.sub("[REDACTED]", result)
    return result


def _last_error_signature(log_tail: str) -> str:
    lines = [line.strip().casefold() for line in log_tail.splitlines() if line.strip()]
    preferred = [
        line
        for line in lines
        if "traceback" in line or "error" in line or "exception" in line
    ]
    source = preferred[-1] if preferred else (lines[-1] if lines else "no-log")
    source = re.sub(r"\b\d+\b", "#", source)
    return source[-500:]


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


__all__ = ("HermesIncident", "HermesIncidentClient", "redact_sensitive")
