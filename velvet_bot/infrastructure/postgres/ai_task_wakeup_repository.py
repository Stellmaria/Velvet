from __future__ import annotations

import asyncio
import logging
import asyncpg

from velvet_bot.database import Database

logger = logging.getLogger(__name__)
AI_TASK_WAKEUP_CHANNEL = "velvet_ai_task_queue"


class PostgresAITaskNotifier:
    """Publish a best-effort queue wake-up after the durable write has committed."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def notify(self) -> None:
        try:
            async with self._database.acquire() as connection:
                await connection.execute(
                    "SELECT pg_notify($1::TEXT, $2::TEXT)",
                    AI_TASK_WAKEUP_CHANNEL,
                    "queued",
                )
        except asyncio.CancelledError:
            raise
        except (asyncpg.PostgresError, OSError, TimeoutError) as error:
            logger.warning(
                "AI task wake-up notification failed; fallback polling remains active: %s",
                error,
            )


class PostgresAITaskQueueDiagnostics:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def oldest_queued_age_seconds(self) -> float | None:
        async with self._database.acquire() as connection:
            value = await connection.fetchval(
                """SELECT EXTRACT(EPOCH FROM (NOW() - MIN(created_at)))
                   FROM ai_tasks
                   WHERE status='queued'"""
            )
        return max(0.0, float(value)) if value is not None else None


class PostgresAITaskListener:
    """Dedicated LISTEN connection with timeout polling and lazy reconnect."""

    def __init__(
        self,
        database_url: str,
        *,
        channel: str = AI_TASK_WAKEUP_CHANNEL,
    ) -> None:
        self._database_url = database_url
        self._channel = channel
        self._connection: asyncpg.Connection | None = None
        self._event = asyncio.Event()
        self._connect_lock = asyncio.Lock()
        self._terminated = False
        self._connected_once = False
        self._wakeups = 0
        self._fallback_polls = 0
        self._reconnects = 0
        self._errors = 0

    @property
    def wakeups(self) -> int:
        return self._wakeups

    @property
    def fallback_polls(self) -> int:
        return self._fallback_polls

    @property
    def reconnects(self) -> int:
        return self._reconnects

    @property
    def errors(self) -> int:
        return self._errors

    def _on_notification(
        self,
        connection: asyncpg.Connection,
        process_id: int,
        channel: str,
        payload: str,
    ) -> None:
        del connection, process_id, channel, payload
        self._event.set()

    def _on_termination(self, connection: asyncpg.Connection) -> None:
        if connection is self._connection:
            self._terminated = True
            self._event.set()

    async def _ensure_connected(self) -> bool:
        async with self._connect_lock:
            connection = self._connection
            if connection is not None and not connection.is_closed() and not self._terminated:
                return True
            await self._discard_connection()
            try:
                connection = await asyncpg.connect(
                    dsn=self._database_url,
                    command_timeout=60,
                )
                await connection.add_listener(self._channel, self._on_notification)
                connection.add_termination_listener(self._on_termination)
            except asyncio.CancelledError:
                raise
            except (asyncpg.PostgresError, OSError, TimeoutError) as error:
                self._errors += 1
                logger.warning(
                    "AI task LISTEN connection unavailable; using bounded polling: %s",
                    error,
                )
                return False
            if self._connected_once:
                self._reconnects += 1
            self._connected_once = True
            self._connection = connection
            self._terminated = False
            return True

    async def _discard_connection(self) -> None:
        connection = self._connection
        self._connection = None
        self._terminated = False
        if connection is None or connection.is_closed():
            return
        try:
            await connection.remove_listener(self._channel, self._on_notification)
            connection.remove_termination_listener(self._on_termination)
            await connection.close()
        except asyncio.CancelledError:
            raise
        except (asyncpg.PostgresError, OSError, TimeoutError):
            self._errors += 1
            logger.debug("Failed to close AI task LISTEN connection", exc_info=True)

    def _consume_notification(self) -> bool:
        if self._terminated:
            self._event.clear()
            return False
        if not self._event.is_set():
            return False
        self._event.clear()
        self._wakeups += 1
        return True

    async def wait(self, timeout_seconds: float) -> bool:
        timeout = max(0.05, float(timeout_seconds))
        if self._consume_notification():
            return True
        if not await self._ensure_connected():
            self._fallback_polls += 1
            await asyncio.sleep(timeout)
            return False
        if self._consume_notification():
            return True
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
        except TimeoutError:
            self._fallback_polls += 1
            return False
        if self._terminated:
            self._event.clear()
            await self._discard_connection()
            self._fallback_polls += 1
            return False
        return self._consume_notification()

    async def close(self) -> None:
        async with self._connect_lock:
            await self._discard_connection()
        self._event.clear()


__all__ = (
    "AI_TASK_WAKEUP_CHANNEL",
    "PostgresAITaskListener",
    "PostgresAITaskNotifier",
    "PostgresAITaskQueueDiagnostics",
)
