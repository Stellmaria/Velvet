from __future__ import annotations

import hashlib
import json
import logging
import os
import platform
import subprocess
import sys
import threading
import zipfile
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BufferedInputFile

from velvet_bot.error_center import ErrorIncident, ErrorIncidentRepository
from velvet_bot.services.system_health import SystemHealthReport, SystemHealthService
from velvet_bot.workers.manager import WorkerManager

logger = logging.getLogger(__name__)

_BUNDLE_SCHEMA = "velvet-diagnostic-bundle/v1"
_MAX_INCIDENTS = 20
_MAX_LOG_ENTRIES = 500
_AUTO_REPEAT_COOLDOWN = timedelta(hours=6)
_AUTO_GLOBAL_COOLDOWN = timedelta(minutes=30)


@dataclass(frozen=True, slots=True)
class DiagnosticBundle:
    filename: str
    payload: bytes
    caption: str
    manifest: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DiagnosticLogEntry:
    created_at: datetime
    level: str
    logger_name: str
    message: str


class DiagnosticLogBuffer(logging.Handler):
    """Bounded, redacted in-memory log tail used only for owner exports."""

    def __init__(self, *, capacity: int = _MAX_LOG_ENTRIES) -> None:
        super().__init__(level=logging.INFO)
        self._entries: deque[DiagnosticLogEntry] = deque(maxlen=max(50, capacity))
        self._entries_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = record.getMessage()
            if record.exc_info:
                formatter = logging.Formatter()
                message = f"{message}\n{formatter.formatException(record.exc_info)}"
            redacted = SystemHealthService.redact_text(message) or ""
            entry = DiagnosticLogEntry(
                created_at=datetime.fromtimestamp(record.created, tz=UTC),
                level=record.levelname.upper(),
                logger_name=record.name,
                message=redacted[-8000:],
            )
            with self._entries_lock:
                self._entries.append(entry)
        except Exception:  # p2-approved-boundary: isolate-diagnostic-log-buffer
            return

    def snapshot(self, *, since: datetime) -> tuple[DiagnosticLogEntry, ...]:
        with self._entries_lock:
            return tuple(item for item in self._entries if item.created_at >= since)


class DiagnosticBundleService:
    """Build safe diagnostic ZIP bundles and deliver critical ones to owners."""

    def __init__(
        self,
        *,
        incident_repository: ErrorIncidentRepository,
        app_version: str,
        owner_user_ids: frozenset[int],
    ) -> None:
        self._incidents = incident_repository
        self._app_version = app_version
        self._owner_user_ids = tuple(sorted(owner_user_ids))
        self._log_buffer = DiagnosticLogBuffer()
        self._logging_started = False
        self._commit_sha = self._resolve_commit_sha()
        self._last_auto_signature: str | None = None
        self._last_auto_sent_at: datetime | None = None
        self._last_auto_any_at: datetime | None = None

    def start(self) -> None:
        if self._logging_started:
            return
        logging.getLogger().addHandler(self._log_buffer)
        self._logging_started = True

    def stop(self) -> None:
        if not self._logging_started:
            return
        logging.getLogger().removeHandler(self._log_buffer)
        self._logging_started = False

    @staticmethod
    def _resolve_commit_sha() -> str:
        for name in ("VELVET_COMMIT_SHA", "GIT_COMMIT_SHA", "GITHUB_SHA"):
            value = os.getenv(name, "").strip()
            if value:
                return value[:40]
        try:
            completed = subprocess.run(
                ("git", "rev-parse", "HEAD"),
                cwd=Path(__file__).resolve().parents[2],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                timeout=2,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return "unknown"
        value = completed.stdout.strip()
        return value[:40] if completed.returncode == 0 and value else "unknown"

    @staticmethod
    def parse_window(value: str | None) -> int:
        cleaned = (value or "24h").strip().casefold()
        aliases = {
            "1": 1,
            "1h": 1,
            "6": 6,
            "6h": 6,
            "24": 24,
            "24h": 24,
            "1d": 24,
            "3d": 72,
            "72h": 72,
            "7d": 168,
            "168h": 168,
        }
        if cleaned not in aliases:
            raise ValueError("Период должен быть 1h, 6h, 24h, 3d или 7d.")
        return aliases[cleaned]

    @staticmethod
    def _incident_dict(incident: ErrorIncident) -> dict[str, Any]:
        return {
            "id": incident.id,
            "fingerprint": incident.fingerprint,
            "severity": incident.severity,
            "logger_name": incident.logger_name,
            "summary": SystemHealthService.redact_text(incident.summary),
            "details": SystemHealthService.redact_text(incident.details),
            "occurrence_count": incident.occurrence_count,
            "first_seen_at": incident.first_seen_at.astimezone(UTC).isoformat(),
            "last_seen_at": incident.last_seen_at.astimezone(UTC).isoformat(),
            "acknowledged_at": (
                incident.acknowledged_at.astimezone(UTC).isoformat()
                if incident.acknowledged_at
                else None
            ),
        }

    @staticmethod
    def _worker_dict(worker: Any) -> dict[str, Any]:
        data = asdict(worker)
        for key, value in tuple(data.items()):
            if isinstance(value, datetime):
                data[key] = value.astimezone(UTC).isoformat()
            elif isinstance(value, str):
                data[key] = SystemHealthService.redact_text(value)
        return data

    @staticmethod
    def _safe_environment() -> dict[str, Any]:
        return {
            "python": platform.python_version(),
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "executable_name": Path(sys.executable).name,
            "process_id": os.getpid(),
            "ai_vision_enabled": os.getenv("AI_VISION_ENABLED", "false").strip().casefold()
            in {"1", "true", "yes", "on", "да"},
            "krita_watermark_enabled": os.getenv(
                "KRITA_WATERMARK_ENABLED", "false"
            ).strip().casefold()
            in {"1", "true", "yes", "on", "да"},
        }

    @staticmethod
    def _summary_markdown(
        *,
        manifest: dict[str, Any],
        report: SystemHealthReport,
        incidents: tuple[ErrorIncident, ...],
        reasons: tuple[str, ...],
    ) -> str:
        lines = [
            "# Velvet Diagnostic Bundle",
            "",
            f"- schema: `{manifest['schema']}`",
            f"- generated_at: `{manifest['generated_at']}`",
            f"- reason: `{manifest['reason']}`",
            f"- window_hours: `{manifest['window_hours']}`",
            f"- app_version: `{manifest['app_version']}`",
            f"- commit_sha: `{manifest['commit_sha']}`",
            f"- health_status: `{report.status}`",
            f"- active_incidents: `{len(incidents)}`",
            "",
            "## Automatic trigger reasons",
            "",
        ]
        lines.extend(f"- {item}" for item in reasons)
        if not reasons:
            lines.append("- manual export")
        lines.extend(
            [
                "",
                "## Contents",
                "",
                "- `manifest.json`: bundle identity and source revision",
                "- `runtime_snapshot.json`: database, Telegram, disk and queue health",
                "- `workers.json`: all registered worker snapshots",
                "- `incidents.json`: active deduplicated Error Center incidents",
                "- `recent_logs.txt`: bounded redacted in-memory log tail",
                "- `environment_safe.json`: non-secret runtime facts",
                "",
                "The bundle intentionally excludes `.env`, tokens, DSN values, database dumps, user media and message bodies.",
            ]
        )
        return "\n".join(lines) + "\n"

    async def build_bundle(
        self,
        *,
        report: SystemHealthReport,
        window_hours: int = 24,
        reason: str = "manual",
        reasons: tuple[str, ...] = (),
    ) -> DiagnosticBundle:
        safe_hours = max(1, min(int(window_hours), 168))
        now = datetime.now(UTC)
        since = now - timedelta(hours=safe_hours)
        incidents = await self._incidents.unacknowledged(limit=_MAX_INCIDENTS)
        logs = self._log_buffer.snapshot(since=since)
        manifest: dict[str, Any] = {
            "schema": _BUNDLE_SCHEMA,
            "generated_at": now.isoformat(),
            "reason": reason,
            "window_hours": safe_hours,
            "app_version": self._app_version,
            "commit_sha": self._commit_sha,
            "health_status": report.status,
            "incident_count": len(incidents),
            "log_entry_count": len(logs),
        }
        runtime = SystemHealthService.report_to_dict(report)
        workers = [self._worker_dict(item) for item in report.workers]
        incident_rows = [self._incident_dict(item) for item in incidents]
        log_text = "\n\n".join(
            (
                f"[{item.created_at.isoformat()}] {item.level} {item.logger_name}\n"
                f"{item.message}"
            )
            for item in logs
        )
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
            archive.writestr(
                "summary.md",
                self._summary_markdown(
                    manifest=manifest,
                    report=report,
                    incidents=incidents,
                    reasons=reasons,
                ),
            )
            archive.writestr(
                "runtime_snapshot.json",
                json.dumps(runtime, ensure_ascii=False, indent=2),
            )
            archive.writestr(
                "workers.json",
                json.dumps(workers, ensure_ascii=False, indent=2),
            )
            archive.writestr(
                "incidents.json",
                json.dumps(incident_rows, ensure_ascii=False, indent=2),
            )
            archive.writestr("recent_logs.txt", log_text)
            archive.writestr(
                "environment_safe.json",
                json.dumps(self._safe_environment(), ensure_ascii=False, indent=2),
            )
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        caption = (
            "<b>Velvet Diagnostic Bundle v1</b>\n\n"
            f"Причина: <code>{reason}</code>\n"
            f"Период: <b>{safe_hours} ч.</b>\n"
            f"Состояние: <code>{report.status}</code>\n"
            f"Commit: <code>{self._commit_sha[:12]}</code>\n\n"
            "Архив очищен от токенов, DSN и секретов. Он не содержит базу, медиа и `.env`."
        )
        return DiagnosticBundle(
            filename=f"velvet_diagnostics_{stamp}.zip",
            payload=buffer.getvalue(),
            caption=caption,
            manifest=manifest,
        )

    async def build_current_bundle(
        self,
        *,
        bot: Bot,
        system_service: SystemHealthService,
        worker_manager: WorkerManager,
        window_hours: int = 24,
        reason: str = "manual",
    ) -> DiagnosticBundle:
        report = await system_service.check(bot=bot, worker_manager=worker_manager)
        return await self.build_bundle(
            report=report,
            window_hours=window_hours,
            reason=reason,
        )

    async def monitor_once(
        self,
        *,
        bot: Bot,
        system_service: SystemHealthService,
        worker_manager: WorkerManager,
    ) -> int:
        if not self._owner_user_ids:
            return 0
        report = await system_service.check(bot=bot, worker_manager=worker_manager)
        incidents = await self._incidents.unacknowledged(limit=_MAX_INCIDENTS)
        reasons: list[str] = []
        if not report.database_ok:
            reasons.append("PostgreSQL недоступна")
        if not report.telegram_ok:
            reasons.append("Telegram API недоступен")
        if report.disk.free_percent < 5:
            reasons.append(f"свободно на диске {report.disk.free_percent:.1f}%")
        failed_workers = [
            item.name
            for item in report.workers
            if item.state == "failed" or item.consecutive_failures >= 3
        ]
        if failed_workers:
            reasons.append("workers с повторными ошибками: " + ", ".join(failed_workers))
        critical = [item for item in incidents if item.severity == "CRITICAL"]
        if critical:
            reasons.append(f"активных CRITICAL-инцидентов: {len(critical)}")
        backup_status = report.database.latest_backup_status if report.database else None
        if backup_status and backup_status.casefold() in {"failed", "error", "invalid"}:
            reasons.append(f"последний backup: {backup_status}")
        if not reasons:
            return 0

        now = datetime.now(UTC)
        signature_source = "|".join(sorted(reasons)) + "|" + "|".join(
            sorted(item.fingerprint for item in critical)
        )
        signature = hashlib.sha256(signature_source.encode("utf-8")).hexdigest()
        if (
            self._last_auto_any_at is not None
            and now - self._last_auto_any_at < _AUTO_GLOBAL_COOLDOWN
        ):
            return 0
        if (
            signature == self._last_auto_signature
            and self._last_auto_sent_at is not None
            and now - self._last_auto_sent_at < _AUTO_REPEAT_COOLDOWN
        ):
            return 0

        bundle = await self.build_bundle(
            report=report,
            window_hours=24,
            reason="automatic-critical",
            reasons=tuple(reasons),
        )
        sent = 0
        for owner_id in self._owner_user_ids:
            try:
                await bot.send_document(
                    chat_id=owner_id,
                    document=BufferedInputFile(bundle.payload, filename=bundle.filename),
                    caption=bundle.caption
                    + "\n\n<b>Триггер:</b> "
                    + "; ".join(reasons)[:1000],
                )
            except TelegramAPIError as error:
                logger.warning(
                    "Could not deliver automatic diagnostic bundle to owner %s: %s",
                    owner_id,
                    error,
                )
                continue
            sent += 1
        if sent:
            self._last_auto_signature = signature
            self._last_auto_sent_at = now
            self._last_auto_any_at = now
        return sent


__all__ = (
    "DiagnosticBundle",
    "DiagnosticBundleService",
    "DiagnosticLogBuffer",
)
