from __future__ import annotations

import logging
from typing import Any

from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)

from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.media_generation.friendly_worker import (
    FriendlyKieGenerationWorker,
    friendly_stage,
)
from velvet_bot.domains.media_generation.models import KieGenerationRequest
from velvet_bot.domains.media_generation.provider_contract import provider_reason_text
from velvet_bot.domains.media_generation.worker import _ProgressMessage, _optional_int

logger = logging.getLogger(__name__)
_INSTALLED = False
_EXTRA_MODEL_CHATTER_MARKERS = (
    "не могу создавать небезопасные изображения",
    "не могу создать небезопасное изображение",
    "не могу генерировать небезопасные изображения",
    "не могу сгенерировать небезопасное изображение",
    "cannot create unsafe images",
    "cannot generate unsafe images",
    "can't create unsafe images",
    "can't generate unsafe images",
)


def _provider_reason_without_unsafe_chatter(value: object) -> str | None:
    """Discard conversational safety refusals that are not provider diagnostics."""

    text = provider_reason_text(value)
    if text is None:
        return None
    normalized = text.casefold()
    if any(marker in normalized for marker in _EXTRA_MODEL_CHATTER_MARKERS):
        return None
    return text


def _log_transient_progress_failure(task_id: object, error: TelegramNetworkError) -> None:
    """Record a temporary Telegram edit failure without opening an ERROR incident."""

    logger.warning(
        "Telegram progress update temporarily failed for %s; generation continues: %s",
        task_id,
        error,
    )


async def _publish_progress_resilient(
    self: FriendlyKieGenerationWorker,
    progress: _ProgressMessage | None,
    *,
    task: AITask,
    request: KieGenerationRequest,
    percent: int,
    stage: str,
    force: bool = False,
) -> None:
    """Update progress best-effort while keeping provider work independent of Telegram."""

    if progress is None:
        return
    safe_percent = max(0, min(100, int(percent)))
    normalized_stage = friendly_stage(request, stage)
    if (
        not force
        and safe_percent == progress.last_percent
        and normalized_stage == progress.last_stage
    ):
        return
    text = self._friendly_progress_text(
        task=task,
        request=request,
        percent=safe_percent,
        stage=normalized_stage,
    )
    try:
        if progress.message_id is None:
            message = await self._bot.send_message(progress.chat_id, text)
            progress.message_id = _optional_int(getattr(message, "message_id", None))
        else:
            await self._bot.edit_message_text(
                text,
                chat_id=progress.chat_id,
                message_id=progress.message_id,
            )
        progress.last_percent = safe_percent
        progress.last_stage = normalized_stage
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            logger.warning(
                "Could not update friendly progress message for %s: %s",
                task.id,
                error,
            )
    except TelegramNetworkError as error:
        _log_transient_progress_failure(task.id, error)
    except TelegramAPIError:
        logger.exception("Could not update friendly progress message for %s", task.id)


def install_telegram_progress_resilience() -> None:
    """Install best-effort Telegram progress updates on the canonical worker."""

    global _INSTALLED
    if _INSTALLED:
        return
    FriendlyKieGenerationWorker._publish_progress = _publish_progress_resilient  # type: ignore[method-assign]
    _INSTALLED = True


__all__ = (
    "_log_transient_progress_failure",
    "_provider_reason_without_unsafe_chatter",
    "install_telegram_progress_resilience",
)
