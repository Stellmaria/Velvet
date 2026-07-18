from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape
from typing import Any

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.database import Database

logger = logging.getLogger(__name__)

_LEVELS = {"WARNING", "ERROR", "CRITICAL"}
_LEVEL_EMOJI = {
    "WARNING": "⚠️",
    "ERROR": "❌",
    "CRITICAL": "🚨",
}
_EXCLUDED_LOGGER_PREFIXES = (
    "velvet_bot.error_center",
    "velvet_bot.audit",
    "velvet_supervisor.notifier",
)
_CONNECTION_URL_RE = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mariadb|redis|mongodb(?:\+srv)?)://[^\s]+",
    re.IGNORECASE,
)
_BOT_TOKEN_RE = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{20,}\b")
_BEARER_RE = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.IGNORECASE)
_SECRET_ASSIGNMENT_RE = re.compile(
    r"\b(?:BOT_TOKEN|DATABASE_URL|PASSWORD|SECRET|API_KEY|SUPERVISOR_TOKEN)\s*=\s*[^\s]+",
    re.IGNORECASE,
)
_DYNAMIC_NUMBER_RE = re.compile(r"\b\d+\b")
_HEX_RE = re.compile(r"0x[0-9a-f]+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class CapturedLog:
    fingerprint: str
    severity: str
    logger_name: str
    summary: str
    details: str | None
    source: str | None


@dataclass(frozen=True, slots=True)
class ErrorIncident:
    id: int
    fingerprint: str
    severity: str
    logger_name: str
    summary: str
    details: str | None
    occurrence_count: int
    first_seen_at: datetime
    last_seen_at: datetime
    acknowledged_at: datetime | None
    acknowledged_by: int | None
    log_chat_message_id: int | None


@dataclass(frozen=True, slots=True)
class RecordedIncident:
    incident: ErrorIncident
    opened: bool


def _redact(value: str | None) -> str | None:
    if value is None:
        return None
    result = _CONNECTION_URL_RE.sub("<redacted-connection-url>", value)
    result = _BOT_TOKEN_RE.sub("<redacted-bot-token>", result)
    result = _BEARER_RE.sub("Bearer <redacted>", result)
    result = _SECRET_ASSIGNMENT_RE.sub("<redacted-secret>", result)
    return result


def _fingerprint(logger_name: str, severity: str, summary: str, exc_name: str) -> str:
    normalized = " ".join(summary.casefold().split())
    normalized = _HEX_RE.sub("<hex>", normalized)
    normalized = _DYNAMIC_NUMBER_RE.sub("<n>", normalized)
    raw = f"{logger_name}|{severity}|{exc_name}|{normalized}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def capture_log_record(record: logging.LogRecord) -> CapturedLog:
    try:
        summary = record.getMessage()
    except Exception:  # p2-approved-boundary: fallback-log-record-message
        summary = str(record.msg)
    summary = (_redact(summary) or "Ошибка без текста")[:1200]

    details: str | None = None
    exc_name = ""
    if record.exc_info:
        exc_type, exc_value, exc_traceback = record.exc_info
        exc_name = getattr(exc_type, "__name__", "Exception")
        details = "".join(
            traceback.format_exception(exc_type, exc_value, exc_traceback)
        )
    elif record.stack_info:
        details = str(record.stack_info)
    details = (_redact(details) or None)
    if details:
        details = details[-6000:]

    severity = record.levelname.upper()
    if severity not in _LEVELS:
        severity = "ERROR" if record.levelno >= logging.ERROR else "WARNING"
    source = f"{record.pathname}:{record.lineno}" if record.pathname else None
    return CapturedLog(
        fingerprint=_fingerprint(record.name, severity, summary, exc_name),
        severity=severity,
        logger_name=record.name,
        summary=summary,
        details=details,
        source=source,
    )


class ErrorIncidentRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    @staticmethod
    def _from_row(row: Any) -> ErrorIncident:
        return ErrorIncident(
            id=int(row["id"]),
            fingerprint=str(row["fingerprint"]),
            severity=str(row["severity"]),
            logger_name=str(row["logger_name"]),
            summary=str(row["summary"]),
            details=str(row["details"]) if row["details"] is not None else None,
            occurrence_count=int(row["occurrence_count"]),
            first_seen_at=row["first_seen_at"],
            last_seen_at=row["last_seen_at"],
            acknowledged_at=row["acknowledged_at"],
            acknowledged_by=(
                int(row["acknowledged_by"])
                if row["acknowledged_by"] is not None
                else None
            ),
            log_chat_message_id=(
                int(row["log_chat_message_id"])
                if row["log_chat_message_id"] is not None
                else None
            ),
        )

    async def record(self, captured: CapturedLog) -> RecordedIncident:
        async with self._database.acquire() as connection:
            async with connection.transaction():
                existing = await connection.fetchrow(
                    """
                    SELECT *
                    FROM error_incidents
                    WHERE fingerprint = $1::CHAR(64)
                    FOR UPDATE
                    """,
                    captured.fingerprint,
                )
                if existing is None:
                    row = await connection.fetchrow(
                        """
                        INSERT INTO error_incidents (
                            fingerprint, severity, logger_name, summary, details
                        )
                        VALUES ($1, $2, $3, $4, $5)
                        RETURNING *
                        """,
                        captured.fingerprint,
                        captured.severity,
                        captured.logger_name[:500],
                        captured.summary,
                        captured.details,
                    )
                    return RecordedIncident(self._from_row(row), opened=True)

                reopened = existing["acknowledged_at"] is not None
                row = await connection.fetchrow(
                    """
                    UPDATE error_incidents
                    SET severity = $2,
                        logger_name = $3,
                        summary = $4,
                        details = $5,
                        occurrence_count = occurrence_count + 1,
                        last_seen_at = NOW(),
                        log_chat_message_id = CASE
                            WHEN acknowledged_at IS NOT NULL THEN NULL
                            ELSE log_chat_message_id
                        END,
                        acknowledged_at = NULL,
                        acknowledged_by = NULL
                    WHERE id = $1
                    RETURNING *
                    """,
                    int(existing["id"]),
                    captured.severity,
                    captured.logger_name[:500],
                    captured.summary,
                    captured.details,
                )
                return RecordedIncident(self._from_row(row), opened=reopened)

    async def set_log_message_id(self, incident_id: int, message_id: int) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE error_incidents
                SET log_chat_message_id = $2,
                    last_seen_at = last_seen_at
                WHERE id = $1
                """,
                int(incident_id),
                int(message_id),
            )

    async def acknowledge(self, incident_id: int, user_id: int) -> ErrorIncident | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                UPDATE error_incidents
                SET acknowledged_at = COALESCE(acknowledged_at, NOW()),
                    acknowledged_by = COALESCE(acknowledged_by, $2)
                WHERE id = $1
                RETURNING *
                """,
                int(incident_id),
                int(user_id),
            )
        return self._from_row(row) if row is not None else None

    async def acknowledge_all(self, user_id: int, *, limit: int = 50) -> tuple[ErrorIncident, ...]:
        safe_limit = max(1, min(int(limit), 100))
        async with self._database.acquire() as connection:
            async with connection.transaction():
                rows = await connection.fetch(
                    """
                    SELECT *
                    FROM error_incidents
                    WHERE acknowledged_at IS NULL
                    ORDER BY last_seen_at DESC, id DESC
                    LIMIT $1
                    FOR UPDATE
                    """,
                    safe_limit,
                )
                await connection.execute(
                    """
                    UPDATE error_incidents
                    SET acknowledged_at = NOW(), acknowledged_by = $1
                    WHERE acknowledged_at IS NULL
                    """,
                    int(user_id),
                )
        return tuple(self._from_row(row) for row in rows)

    async def unacknowledged(self, *, limit: int = 5) -> tuple[ErrorIncident, ...]:
        safe_limit = max(1, min(int(limit), 20))
        async with self._database.acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT *
                FROM error_incidents
                WHERE acknowledged_at IS NULL
                ORDER BY CASE severity
                            WHEN 'CRITICAL' THEN 3
                            WHEN 'ERROR' THEN 2
                            ELSE 1
                         END DESC,
                         last_seen_at DESC,
                         id DESC
                LIMIT $1
                """,
                safe_limit,
            )
        return tuple(self._from_row(row) for row in rows)

    async def unacknowledged_counts(self) -> dict[str, int]:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE severity = 'WARNING') AS warnings,
                    COUNT(*) FILTER (WHERE severity = 'ERROR') AS errors,
                    COUNT(*) FILTER (WHERE severity = 'CRITICAL') AS critical
                FROM error_incidents
                WHERE acknowledged_at IS NULL
                """
            )
        return {
            "total": int(row["total"] or 0),
            "warnings": int(row["warnings"] or 0),
            "errors": int(row["errors"] or 0),
            "critical": int(row["critical"] or 0),
        }

    async def digest_due(self, *, cooldown_seconds: int) -> bool:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                "SELECT last_owner_digest_at FROM error_alert_state WHERE id = 1"
            )
        if value is None:
            return True
        return datetime.now(UTC) - value >= timedelta(seconds=max(1, cooldown_seconds))

    async def mark_digest_sent(self) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO error_alert_state (id, last_owner_digest_at, updated_at)
                VALUES (1, NOW(), NOW())
                ON CONFLICT (id) DO UPDATE
                SET last_owner_digest_at = EXCLUDED.last_owner_digest_at,
                    updated_at = NOW()
                """
            )


def _is_recoverable_aiogram_polling_record(record: logging.LogRecord) -> bool:
    if record.name != "aiogram.dispatcher":
        return False
    try:
        message = record.getMessage().casefold()
    except Exception:  # p2-approved-boundary: fallback-polling-record-message
        message = str(record.msg).casefold()
    return (
        "failed to fetch updates" in message
        and "telegramnetworkerror" in message
        and (
            "serverdisconnectederror" in message
            or "server disconnected" in message
        )
    )


class ErrorLoggingHandler(logging.Handler):
    def __init__(self, center: "ErrorIncidentCenter") -> None:
        super().__init__(level=logging.WARNING)
        self._center = center

    def emit(self, record: logging.LogRecord) -> None:
        if record.levelno < logging.WARNING:
            return
        if _is_recoverable_aiogram_polling_record(record):
            return
        if record.name.startswith(_EXCLUDED_LOGGER_PREFIXES):
            return
        try:
            captured = capture_log_record(record)
            self._center.enqueue_threadsafe(captured)
        except Exception:  # p2-approved-boundary: isolate-error-logging-handler
            # A logging handler must never break the application it observes.
            return


class ErrorIncidentCenter:
    def __init__(
        self,
        *,
        bot: Bot,
        repository: ErrorIncidentRepository,
        log_chat_id: int | None,
        owner_user_ids: frozenset[int],
    ) -> None:
        self._bot = bot
        self._repository = repository
        self._log_chat_id = log_chat_id
        self._owner_user_ids = tuple(sorted(owner_user_ids))
        self._queue: asyncio.Queue[CapturedLog] = asyncio.Queue(maxsize=1000)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._consumer_task: asyncio.Task[None] | None = None
        self._handler: ErrorLoggingHandler | None = None
        self._dropped = 0

    async def start(self) -> None:
        if self._consumer_task is not None:
            return
        self._loop = asyncio.get_running_loop()
        self._handler = ErrorLoggingHandler(self)
        logging.getLogger().addHandler(self._handler)
        self._consumer_task = asyncio.create_task(
            self._consume(),
            name="error-incident-center",
        )

    async def stop(self) -> None:
        if self._handler is not None:
            logging.getLogger().removeHandler(self._handler)
            self._handler = None
        try:
            await asyncio.wait_for(self._queue.join(), timeout=3)
        except TimeoutError:
            pass
        if self._consumer_task is not None:
            self._consumer_task.cancel()
            await asyncio.gather(self._consumer_task, return_exceptions=True)
            self._consumer_task = None
        self._loop = None

    def enqueue_threadsafe(self, captured: CapturedLog) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        try:
            loop.call_soon_threadsafe(self._enqueue_nowait, captured)
        except RuntimeError:
            return

    def _enqueue_nowait(self, captured: CapturedLog) -> None:
        try:
            self._queue.put_nowait(captured)
        except asyncio.QueueFull:
            self._dropped += 1

    async def report_exception(
        self,
        title: str,
        error: BaseException,
        *,
        severity: str = "CRITICAL",
        logger_name: str = "velvet_bot.application",
    ) -> None:
        details = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        summary = f"{title}: {error}"
        captured = CapturedLog(
            fingerprint=_fingerprint(
                logger_name,
                severity,
                summary,
                type(error).__name__,
            ),
            severity=severity if severity in _LEVELS else "CRITICAL",
            logger_name=logger_name,
            summary=(_redact(summary) or title)[:1200],
            details=(_redact(details) or None),
            source=None,
        )
        await self._process(captured)

    async def _consume(self) -> None:
        while True:
            captured = await self._queue.get()
            try:
                await self._process(captured)
            except asyncio.CancelledError:
                raise
            except Exception as error:  # p2-approved-boundary: isolate-error-incident-item
                logger.warning("Error incident processing failed: %s", error)
            finally:
                self._queue.task_done()

    async def _process(self, captured: CapturedLog) -> None:
        recorded = await self._repository.record(captured)
        incident = recorded.incident
        await self._publish_to_log_chat(incident)
        if recorded.opened:
            await self._send_owner_digest(cooldown_seconds=120)

    @staticmethod
    def _incident_markup(incident_id: int) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Прочитано / беру в работу",
                        callback_data=f"err:ack:{incident_id}",
                    )
                ]
            ]
        )

    @staticmethod
    def _format_time(value: datetime | None) -> str:
        if value is None:
            return "—"
        return value.astimezone(UTC).strftime("%d.%m.%Y %H:%M:%S UTC")

    def _render_incident(self, incident: ErrorIncident) -> str:
        emoji = _LEVEL_EMOJI.get(incident.severity, "❗")
        lines = [
            f"<b>{emoji} Ошибка #{incident.id}</b>",
            f"<b>Уровень:</b> <code>{escape(incident.severity)}</code>",
            f"<b>Модуль:</b> <code>{escape(incident.logger_name)}</code>",
            f"<b>Повторов:</b> <code>{incident.occurrence_count}</code>",
            f"<b>Впервые:</b> <code>{self._format_time(incident.first_seen_at)}</code>",
            f"<b>Последний раз:</b> <code>{self._format_time(incident.last_seen_at)}</code>",
            "",
            f"<b>Сообщение:</b>\n<code>{escape(incident.summary)}</code>",
        ]
        if incident.details:
            reserved = len("\n".join(lines)) + 160
            details = incident.details[-max(300, 3900 - reserved):]
            lines.extend(["", f"<b>Traceback:</b>\n<pre>{escape(details)}</pre>"])
        if incident.acknowledged_at is not None:
            lines.extend(
                [
                    "",
                    "<b>✅ Отмечено просмотренным</b>",
                    f"<b>Кем:</b> <code>{incident.acknowledged_by or '—'}</code>",
                    f"<b>Когда:</b> <code>{self._format_time(incident.acknowledged_at)}</code>",
                ]
            )
        text = "\n".join(lines)
        return text[:4090]

    async def _publish_to_log_chat(self, incident: ErrorIncident) -> None:
        if self._log_chat_id is None:
            return
        text = self._render_incident(incident)
        markup = self._incident_markup(incident.id)
        if incident.log_chat_message_id is not None:
            try:
                await self._bot.edit_message_text(
                    chat_id=self._log_chat_id,
                    message_id=incident.log_chat_message_id,
                    text=text,
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )
                return
            except TelegramBadRequest as error:
                if "message is not modified" in str(error).casefold():
                    return
            except TelegramAPIError:
                pass

        try:
            message = await self._bot.send_message(
                chat_id=self._log_chat_id,
                text=text,
                reply_markup=markup,
                disable_web_page_preview=True,
                disable_notification=incident.severity == "WARNING",
            )
        except TelegramAPIError as error:
            logger.warning("Could not publish incident %s to log chat: %s", incident.id, error)
            return
        await self._repository.set_log_message_id(incident.id, message.message_id)

    async def _send_owner_digest(self, *, cooldown_seconds: int) -> int:
        if not self._owner_user_ids:
            return 0
        counts = await self._repository.unacknowledged_counts()
        if counts["total"] <= 0:
            return 0
        if not await self._repository.digest_due(cooldown_seconds=cooldown_seconds):
            return 0
        incidents = await self._repository.unacknowledged(limit=5)
        lines = [
            "<b>🚨 В лог-чате есть непросмотренные ошибки</b>",
            "",
            f"Всего: <b>{counts['total']}</b>",
            f"Критических: <b>{counts['critical']}</b>",
            f"Ошибок: <b>{counts['errors']}</b>",
            f"Предупреждений: <b>{counts['warnings']}</b>",
        ]
        if incidents:
            lines.extend(["", "<b>Последние:</b>"])
            for incident in incidents:
                summary = incident.summary.replace("\n", " ")[:180]
                lines.append(
                    f"• #{incident.id} {escape(incident.severity)} · "
                    f"{escape(summary)} · ×{incident.occurrence_count}"
                )
        lines.extend(
            [
                "",
                "Откройте лог-чат и нажмите под ошибкой «Прочитано / беру в работу».",
            ]
        )
        markup = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Всё просмотрено",
                        callback_data="err:ackall",
                    )
                ]
            ]
        )
        sent = 0
        for owner_id in self._owner_user_ids:
            try:
                await self._bot.send_message(
                    chat_id=owner_id,
                    text="\n".join(lines)[:4090],
                    reply_markup=markup,
                    disable_web_page_preview=True,
                )
                sent += 1
            except TelegramAPIError as error:
                logger.warning("Could not notify owner %s about incidents: %s", owner_id, error)
        if sent:
            await self._repository.mark_digest_sent()
        return sent

    async def send_owner_reminder_once(self) -> int:
        return await self._send_owner_digest(cooldown_seconds=1800)

    async def acknowledge_incident(self, incident_id: int, user_id: int) -> bool:
        incident = await self._repository.acknowledge(incident_id, user_id)
        if incident is None:
            return False
        if self._log_chat_id is not None and incident.log_chat_message_id is not None:
            try:
                await self._bot.edit_message_text(
                    chat_id=self._log_chat_id,
                    message_id=incident.log_chat_message_id,
                    text=self._render_incident(incident),
                    reply_markup=None,
                    disable_web_page_preview=True,
                )
            except TelegramBadRequest as error:
                if "message is not modified" not in str(error).casefold():
                    logger.warning("Could not mark incident message acknowledged: %s", error)
            except TelegramAPIError as error:
                logger.warning("Could not mark incident message acknowledged: %s", error)
        return True

    async def acknowledge_all(self, user_id: int) -> int:
        incidents = await self._repository.acknowledge_all(user_id)
        for incident in incidents:
            if self._log_chat_id is None or incident.log_chat_message_id is None:
                continue
            acknowledged = await self._repository.acknowledge(incident.id, user_id)
            if acknowledged is None:
                continue
            try:
                await self._bot.edit_message_text(
                    chat_id=self._log_chat_id,
                    message_id=acknowledged.log_chat_message_id,
                    text=self._render_incident(acknowledged),
                    reply_markup=None,
                    disable_web_page_preview=True,
                )
            except TelegramAPIError:
                continue
        return len(incidents)


__all__ = (
    "CapturedLog",
    "ErrorIncident",
    "ErrorIncidentCenter",
    "ErrorIncidentRepository",
    "ErrorLoggingHandler",
    "capture_log_record",
)
