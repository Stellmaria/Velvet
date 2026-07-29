from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict
from html import escape
from pathlib import Path
from typing import Any

from aiogram.exceptions import TelegramAPIError

import velvet_bot.app.grs_resilience as grs_resilience
from velvet_bot.app.grs_campaign_retry import CampaignGrsGenerationWorker
from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.models import KieGenerationRequest
from velvet_bot.domains.media_generation.worker import (
    KieGenerationWorker as BaseKieGenerationWorker,
)
from velvet_bot.domains.media_generation.worker import _ProgressMessage, _optional_int
from velvet_bot.infrastructure.ai import KieClient

_REFERENCE_CACHE_TTL_SECONDS = 20 * 60
_REFERENCE_CACHE_MAX_ENTRIES = 256
_REFERENCE_UPLOAD_CONCURRENCY = 3
_MAX_POLL_INTERVAL_SECONDS = 2.0
_GRS_BALANCE_LINE = re.compile(r"(?m)^Баланс GRS:.*(?:\n|$)")

_INSTALLED = False
_ORIGINAL_CLIENT_INIT = KieClient.__init__
_ORIGINAL_FRIENDLY_TEXT = FriendlyKieGenerationWorker._friendly_progress_text

# Temporary provider URLs are deliberately cached only in memory and only briefly.
# A process restart or the short TTL automatically discards stale entries.
_REFERENCE_URL_CACHE: OrderedDict[str, tuple[float, str]] = OrderedDict()
_REFERENCE_CACHE_LOCK = asyncio.Lock()


def _reference_cache_key(reference: object) -> str:
    unique_id = str(getattr(reference, "telegram_file_unique_id", "") or "").strip()
    file_id = str(getattr(reference, "telegram_file_id", "") or "").strip()
    mime_type = str(getattr(reference, "mime_type", "") or "").strip().casefold()
    file_size = str(getattr(reference, "file_size", "") or "").strip()
    return "|".join((unique_id or file_id, mime_type, file_size))


async def _cached_reference_url(key: str) -> str | None:
    now = time.monotonic()
    async with _REFERENCE_CACHE_LOCK:
        expired = [
            cache_key
            for cache_key, (expires_at, _) in _REFERENCE_URL_CACHE.items()
            if expires_at <= now
        ]
        for cache_key in expired:
            _REFERENCE_URL_CACHE.pop(cache_key, None)
        cached = _REFERENCE_URL_CACHE.get(key)
        if cached is None:
            return None
        expires_at, url = cached
        if expires_at <= now:
            _REFERENCE_URL_CACHE.pop(key, None)
            return None
        _REFERENCE_URL_CACHE.move_to_end(key)
        return url


async def _remember_reference_url(key: str, url: str) -> None:
    async with _REFERENCE_CACHE_LOCK:
        _REFERENCE_URL_CACHE[key] = (
            time.monotonic() + _REFERENCE_CACHE_TTL_SECONDS,
            url,
        )
        _REFERENCE_URL_CACHE.move_to_end(key)
        while len(_REFERENCE_URL_CACHE) > _REFERENCE_CACHE_MAX_ENTRIES:
            _REFERENCE_URL_CACHE.popitem(last=False)


def _fast_client_init(self: KieClient, *args: Any, **kwargs: Any) -> None:
    configured = float(kwargs.get("poll_interval_seconds", 4))
    kwargs["poll_interval_seconds"] = min(
        configured,
        _MAX_POLL_INTERVAL_SECONDS,
    )
    _ORIGINAL_CLIENT_INIT(self, *args, **kwargs)


async def _fast_start_progress(
    self: FriendlyKieGenerationWorker,
    *,
    task: AITask,
    request: KieGenerationRequest,
) -> _ProgressMessage | None:
    """Create progress immediately without a blocking GRS balance request."""

    chat_id = _optional_int(task.payload.get("chat_id"))
    if chat_id is None:
        return None

    stage = "Задача принята. Готовлю всё для генерации."
    text = self._friendly_progress_text(
        task=task,
        request=request,
        percent=0,
        stage=stage,
    )
    try:
        message = await self._bot.send_message(chat_id, text)
    except TelegramAPIError:
        return None
    return _ProgressMessage(
        chat_id=chat_id,
        message_id=_optional_int(getattr(message, "message_id", None)),
        last_percent=0,
        last_stage=stage,
    )


def _fast_friendly_text(
    self: FriendlyKieGenerationWorker,
    *,
    task: AITask,
    request: KieGenerationRequest,
    percent: int,
    stage: str,
) -> str:
    text = _ORIGINAL_FRIENDLY_TEXT(
        self,
        task=task,
        request=request,
        percent=percent,
        stage=stage,
    )
    text = _GRS_BALANCE_LINE.sub("", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


async def _fast_upload_references(
    self: BaseKieGenerationWorker,
    *,
    queue_task_id: object,
    request: KieGenerationRequest,
    task: AITask,
    progress: _ProgressMessage | None,
) -> KieGenerationRequest:
    """Reuse recent uploads and prepare independent references concurrently."""

    if not request.references:
        await self._publish_progress(
            progress,
            task=task,
            request=request,
            percent=35,
            stage="Референсы не требуются.",
        )
        return request

    total = len(request.references)
    await self._publish_progress(
        progress,
        task=task,
        request=request,
        percent=10,
        stage=f"Параллельно подготавливаю референсы: {total} шт.",
    )
    semaphore = asyncio.Semaphore(_REFERENCE_UPLOAD_CONCURRENCY)

    async def prepare(index: int, reference: object) -> str:
        key = _reference_cache_key(reference)
        cached = await _cached_reference_url(key)
        if cached is not None:
            return cached

        async with semaphore:
            cached_after_wait = await _cached_reference_url(key)
            if cached_after_wait is not None:
                return cached_after_wait
            payload = await self._download_reference(reference)
            safe_name = Path(
                str(
                    getattr(reference, "file_name", "reference.jpg")
                    or "reference.jpg"
                )
            ).name
            uploaded = await self._client.upload_reference(
                payload,
                mime_type=str(getattr(reference, "mime_type", "image/jpeg")),
                file_name=f"{queue_task_id}-{index}-{safe_name}",
            )
            await _remember_reference_url(key, uploaded.file_url)
            return uploaded.file_url

    urls = await asyncio.gather(
        *(
            prepare(index, reference)
            for index, reference in enumerate(request.references, start=1)
        )
    )
    await self._queue.heartbeat(
        task_id=queue_task_id,
        worker_id=self._worker_id,
    )
    await self._publish_progress(
        progress,
        task=task,
        request=request,
        percent=35,
        stage=f"Референсы готовы: {total}/{total}.",
    )
    return request.with_image_urls(tuple(urls))


async def _notify_terminal_without_balance(
    self: CampaignGrsGenerationWorker,
    task: AITask,
    error: Exception,
) -> None:
    """Report a failed GRS campaign without another provider balance request."""

    if not grs_resilience._is_grs_violation_error(error):
        await grs_resilience.ResilientFriendlyKieGenerationWorker._notify_terminal_failure_best_effort(
            self,
            task,
            error,
        )
        return

    chat_id = _optional_int(task.payload.get("chat_id"))
    if chat_id is None:
        return
    reason = grs_resilience._grs_violation_reason_from_error(error)
    reason_line = (
        f"<b>Причина GRS AI:</b> {escape(reason)}"
        if reason is not None
        else (
            "<b>Причина:</b> GRS AI не передал технической категории. "
            "Текстовый ответ модели отброшен как недостоверная диагностика."
        )
    )
    attempts = max(1, int(task.attempt_count))
    try:
        await self._bot.send_message(
            chat_id,
            "<b>Ауф не смог завершить генерацию</b>\n\n"
            "Провайдер: <b>GRS AI</b>\n"
            f"Последовательная кампания исчерпала <b>{attempts}/{task.max_attempts}</b> попыток.\n"
            f"{reason_line}\n\n"
            "Баланс не проверялся автоматически. Он доступен отдельной кнопкой.\n"
            "Параллельные платные задачи не запускались.\n"
            f"Задача: <code>{task.id}</code>",
        )
    except TelegramAPIError:
        return
    finally:
        self._provider_balances.pop(str(task.id), None)


def install_grs_speedups() -> None:
    """Install latency reductions without changing provider billing semantics."""

    global _INSTALLED
    if _INSTALLED:
        return
    KieClient.__init__ = _fast_client_init  # type: ignore[method-assign]
    FriendlyKieGenerationWorker._start_progress = (  # type: ignore[method-assign]
        _fast_start_progress
    )
    FriendlyKieGenerationWorker._friendly_progress_text = (  # type: ignore[method-assign]
        _fast_friendly_text
    )
    BaseKieGenerationWorker._upload_references = (  # type: ignore[method-assign]
        _fast_upload_references
    )
    CampaignGrsGenerationWorker._notify_terminal_failure_best_effort = (  # type: ignore[method-assign]
        _notify_terminal_without_balance
    )
    _INSTALLED = True


__all__ = ("install_grs_speedups",)
