from __future__ import annotations

import asyncio
import importlib
import json
import re
import urllib.parse
from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram.exceptions import TelegramAPIError
from asyncpg import PostgresError

from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.media_generation.friendly_worker import (
    FriendlyKieGenerationWorker,
    _request_from_payload,
)
from velvet_bot.domains.media_generation.models import (
    KieGenerationRequest,
    KieTaskRecord,
    KieTaskState,
)
from velvet_bot.domains.media_generation.task_queue import KieTaskQueueService
from velvet_bot.domains.media_generation.worker import _ProgressMessage, _optional_int
from velvet_bot.infrastructure.ai import (
    KieClient,
    KieError,
    KieTaskFailed,
    KieTransientError,
)

_GRS_VIOLATION_STATUSES = frozenset(
    {
        "violation",
        "content_violation",
        "moderation_violation",
        "moderated",
    }
)
_GRS_VIOLATION_MAX_PROVIDER_ATTEMPTS = 2
_CREDIT_KEYS = frozenset(
    {
        "credits",
        "credit",
        "balance",
        "currentcredits",
        "apikeycredits",
        "remainingcredits",
        "remaincredits",
        "availablecredits",
        "leftcredits",
    }
)
_INSTALLED = False
_ORIGINAL_FROM_GRS_API = KieTaskRecord.from_grs_api.__func__
_ORIGINAL_QUEUE_FAIL = KieTaskQueueService.fail


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def _decimal_value(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, Mapping) or isinstance(value, (list, tuple, set)):
        return None
    text = str(value).strip().replace(" ", "").replace(",", "")
    if not text:
        return None
    try:
        parsed = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not parsed.is_finite() or parsed < 0:
        return None
    return parsed


def _extract_grs_credits(value: object) -> Decimal | None:
    direct = _decimal_value(value)
    if direct is not None:
        return direct
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _normalized_key(key) in _CREDIT_KEYS:
                parsed = _decimal_value(item)
                if parsed is not None:
                    return parsed
        for container_key in ("data", "result", "payload", "account", "apiKey"):
            if container_key in value:
                parsed = _extract_grs_credits(value[container_key])
                if parsed is not None:
                    return parsed
        for item in value.values():
            if isinstance(item, Mapping):
                parsed = _extract_grs_credits(item)
                if parsed is not None:
                    return parsed
    return None


async def _get_grs_credits_resilient(client: KieClient) -> Decimal:
    """Read the API-key balance through the documented endpoint and fallbacks."""

    api_key = client.grs_api_key
    if api_key is None:
        raise KieError("Для проверки баланса не задан GRS_API_KEY.")

    query = urllib.parse.urlencode({"apikey": api_key})
    attempts: tuple[tuple[str, str, Mapping[str, object] | None], ...] = (
        (
            "GET",
            f"{client.grs_base_url}/client/common/getCredits?{query}",
            None,
        ),
        (
            "POST",
            f"{client.grs_base_url}/client/openapi/getAPIKeyCredits",
            {"apikey": api_key},
        ),
        (
            "POST",
            f"{client.grs_base_url}/client/openapi/getAPIKeyCredits",
            {"apiKey": api_key},
        ),
    )
    for method, url, payload in attempts:
        try:
            response = await asyncio.to_thread(
                client._transport,
                method,
                url,
                client._headers(api_key),
                payload,
                client.timeout_seconds,
            )
        except KieError:
            continue
        credits = _extract_grs_credits(response)
        if credits is not None:
            return credits
    raise KieTransientError("Не удалось получить текущий баланс GRS AI.")


def _from_grs_api_with_violation(
    cls: type[KieTaskRecord],
    payload: Mapping[str, Any],
    *,
    task_id: str | None = None,
) -> KieTaskRecord:
    status = str(payload.get("status") or "").strip().casefold()
    if status not in _GRS_VIOLATION_STATUSES:
        return _ORIGINAL_FROM_GRS_API(cls, payload, task_id=task_id)

    normalized = dict(payload)
    normalized["status"] = "failed"
    message = str(
        payload.get("message")
        or payload.get("msg")
        or "Запрос отклонён модерацией GRS AI."
    ).strip()
    failure = payload.get("error")
    if isinstance(failure, Mapping):
        failure_payload = dict(failure)
        failure_payload.setdefault("code", status)
        failure_payload.setdefault("message", message)
        normalized["error"] = failure_payload
    elif failure:
        normalized["error"] = {"code": status, "message": str(failure)}
    else:
        normalized["error"] = {"code": status, "message": message}

    record = _ORIGINAL_FROM_GRS_API(cls, normalized, task_id=task_id)
    return replace(
        record,
        state=KieTaskState.FAIL,
        failure_code=record.failure_code or status,
        failure_message=record.failure_message or message,
        raw=dict(payload),
    )


def _is_grs_violation_record(record: KieTaskRecord) -> bool:
    if not record.task_id.startswith("grs:"):
        return False
    raw_status = str(record.raw.get("status") or "").strip().casefold()
    if raw_status in _GRS_VIOLATION_STATUSES:
        return True
    details = " ".join(
        str(value or "")
        for value in (
            record.failure_code,
            record.failure_message,
            record.raw.get("code"),
            record.raw.get("message"),
            record.raw.get("msg"),
            record.raw.get("error"),
        )
    ).casefold()
    return "violation" in details or "moderation" in details


def _is_grs_violation_error(error: BaseException) -> bool:
    return isinstance(error, KieTaskFailed) and _is_grs_violation_record(error.record)


def _provider_attempt_from_payload(payload: object) -> int:
    parsed_payload = payload
    if isinstance(parsed_payload, str):
        try:
            parsed_payload = json.loads(parsed_payload)
        except json.JSONDecodeError:
            return 0
    if not isinstance(parsed_payload, Mapping):
        return 0
    runtime = parsed_payload.get("kie_campaign")
    if isinstance(runtime, str):
        try:
            runtime = json.loads(runtime)
        except json.JSONDecodeError:
            return 0
    if not isinstance(runtime, Mapping):
        return 0
    try:
        return max(0, int(str(runtime.get("provider_attempt_count") or "0")))
    except (TypeError, ValueError):
        return 0


def _violation_retry_limit_reached(error: BaseException, provider_attempt: int) -> bool:
    return _is_grs_violation_error(error) and (
        provider_attempt >= _GRS_VIOLATION_MAX_PROVIDER_ATTEMPTS
    )


async def _queue_fail_with_grs_violation_limit(
    queue: KieTaskQueueService,
    *,
    task_id,
    worker_id: str,
    error: BaseException,
    base_delay_seconds: int,
    max_delay_seconds: int,
):
    if _is_grs_violation_error(error):
        provider_attempt = 0
        try:
            async with queue._database.acquire() as connection:
                row = await connection.fetchrow(
                    "SELECT payload FROM ai_tasks WHERE id=$1::UUID",
                    task_id,
                )
            provider_attempt = _provider_attempt_from_payload(
                row["payload"] if row is not None else None
            )
        except (PostgresError, KeyError, TypeError, ValueError, RuntimeError, OSError):
            provider_attempt = 0
        if _violation_retry_limit_reached(error, provider_attempt):
            return await queue.fail_terminal(
                task_id=task_id,
                worker_id=worker_id,
                error=error,
            )
    return await _ORIGINAL_QUEUE_FAIL(
        queue,
        task_id=task_id,
        worker_id=worker_id,
        error=error,
        base_delay_seconds=base_delay_seconds,
        max_delay_seconds=max_delay_seconds,
    )


class ResilientFriendlyKieGenerationWorker(FriendlyKieGenerationWorker):
    """Add one bounded moderation retry and a live terminal GRS balance."""

    def _friendly_progress_text(
        self,
        *,
        task: AITask,
        request: KieGenerationRequest,
        percent: int,
        stage: str,
    ) -> str:
        text = super()._friendly_progress_text(
            task=task,
            request=request,
            percent=percent,
            stage=stage,
        )
        if request.model.is_grs:
            text = text.replace(
                f"Контент: <b>{request.content_mode.display_name}</b>",
                f"Контент: <b>{request.content_mode.display_name}</b> · модерация GRS активна",
            )
        return text

    async def _report_retry_or_terminal(
        self,
        *,
        task: AITask,
        request: KieGenerationRequest | None,
        progress: _ProgressMessage | None,
        failure: object,
        provider_attempt: int,
        error: Exception,
    ) -> None:
        if not _is_grs_violation_error(error):
            await super()._report_retry_or_terminal(
                task=task,
                request=request,
                progress=progress,
                failure=failure,
                provider_attempt=provider_attempt,
                error=error,
            )
            return

        will_retry = bool(getattr(failure, "will_retry", False))
        if request is not None and will_retry:
            delay = int(getattr(failure, "retry_delay_seconds", 0) or 0)
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=max(5, progress.last_percent if progress else 5),
                stage=(
                    "GRS AI отклонил первую попытку модерацией. "
                    f"Автоматически повторяю один раз через {delay} сек."
                ),
                force=True,
            )
            return

        if request is not None:
            await self._publish_progress(
                progress,
                task=task,
                request=request,
                percent=100,
                stage=(
                    "GRS AI повторно отклонил запрос модерацией. "
                    "Новые платные отправки остановлены."
                ),
                force=True,
            )
        await self._notify_terminal_failure_best_effort(task, error)

    async def _notify_terminal_failure_best_effort(
        self,
        task: AITask,
        error: Exception,
    ) -> None:
        if not _is_grs_violation_error(error):
            await super()._notify_terminal_failure_best_effort(task, error)
            return

        chat_id = _optional_int(task.payload.get("chat_id"))
        if chat_id is None:
            return
        request = _request_from_payload(task.payload)
        balance: Decimal | None = None
        try:
            balance = await self._client.get_grs_credits()
        except KieError:
            balance = None
        balance_line = (
            f"Баланс GRS после остановки: <b>{_format_credits(balance)}</b> кредитов"
            if balance is not None
            else "Баланс GRS после остановки: <b>не удалось проверить</b>"
        )
        try:
            await self._bot.send_message(
                chat_id,
                "<b>Мяу не смог завершить генерацию</b>\n\n"
                "Провайдер: <b>GRS AI</b>\n"
                "Запрос дважды отклонён модерацией провайдера.\n"
                "Автоматический повтор: <b>выполнен 1 раз</b>\n"
                f"{balance_line}\n\n"
                "Режим Mature не отключает модерацию Nano Banana. "
                "Окончательное возвращение кредитов может отразиться с задержкой.\n"
                f"Задача: <code>{task.id}</code>",
            )
        except TelegramAPIError:
            return
        finally:
            self._provider_balances.pop(str(task.id), None)


def _format_credits(value: Decimal) -> str:
    return f"{int(value.quantize(Decimal('1'))):,}".replace(",", " ")


def install_grs_resilience() -> None:
    """Install GRS status, retry and balance compatibility before workers start."""

    global _INSTALLED
    if _INSTALLED:
        return
    KieTaskRecord.from_grs_api = classmethod(_from_grs_api_with_violation)  # type: ignore[method-assign]
    KieTaskQueueService.fail = _queue_fail_with_grs_violation_limit  # type: ignore[method-assign]
    KieClient.get_grs_credits = _get_grs_credits_resilient  # type: ignore[method-assign]
    workers = importlib.import_module("velvet_bot.app.workers")
    workers.KieGenerationWorker = ResilientFriendlyKieGenerationWorker
    _INSTALLED = True


__all__ = (
    "ResilientFriendlyKieGenerationWorker",
    "install_grs_resilience",
)
