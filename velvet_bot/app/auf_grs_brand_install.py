from __future__ import annotations

import re
from html import escape

from aiogram.exceptions import TelegramAPIError

import velvet_bot.app.grs_resilience as grs_resilience
from velvet_bot.app.grs_campaign_retry import CampaignGrsGenerationWorker
from velvet_bot.domains.ai_usage import AITask
from velvet_bot.domains.media_generation.friendly_worker import FriendlyKieGenerationWorker
from velvet_bot.domains.media_generation.models import KieGenerationRequest, KieTaskRecord
from velvet_bot.domains.media_generation.worker import (
    KieGenerationWorker as BaseKieGenerationWorker,
)

_INSTALLED = False


def _sanitize_auf_text(text: str) -> str:
    """Remove retired setup prose and normalize visible product branding."""

    cleaned = re.sub(
        r"(?m)^Контент: <b>Mature</b>(?: · модерация GRS активна)?\n?",
        "",
        str(text),
    )
    legacy_queue = (
        "Задача поставлена в очередь. Worker скачает выбранные Telegram-фото, "
        "временно загрузит их в Kie и только затем вызовет модель."
    )
    if legacy_queue in cleaned:
        destination = "GRS AI" if "Nano Banana" in cleaned else "выбранному провайдеру"
        cleaned = cleaned.replace(
            legacy_queue,
            "Задача поставлена в очередь. Референсы будут подготовлены "
            f"и затем отправлены в {destination}.",
        )
    legacy_mature_paragraph = (
        "Mature-режим включён. Для Seedream бот передаст документированный "
        "<code>nsfw_checker=false</code>. У Nano Banana Pro отдельного API-флага "
        "отключения фильтра нет, поэтому действует политика самого провайдера."
    )
    cleaned = cleaned.replace(
        legacy_mature_paragraph,
        "После выбора модели будут показаны доступные варианты качества.",
    )
    cleaned = (
        cleaned.replace("🐈 <b>Мяу</b>", "🐕 <b>Ауф</b>")
        .replace("🐈 Мяу", "🐕 Ауф")
        .replace("МЯУ", "АУФ")
        .replace("Мяу", "Ауф")
        .replace("мяу", "ауф")
        .replace("MEOW", "AUF")
        .replace("Meow", "Auf")
    )
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def _friendly_progress_text_auf(
    self: FriendlyKieGenerationWorker,
    *,
    task: AITask,
    request: KieGenerationRequest,
    percent: int,
    stage: str,
) -> str:
    text = FriendlyKieGenerationWorker._friendly_progress_text(
        self,
        task=task,
        request=request,
        percent=percent,
        stage=stage,
    )
    return _sanitize_auf_text(text)


async def _deliver_best_effort_auf(
    self: FriendlyKieGenerationWorker,
    *,
    chat_id: int | None,
    request: KieGenerationRequest,
    record: KieTaskRecord,
) -> None:
    if chat_id is None:
        return
    provider = "GRS AI" if request.model.is_grs else "Kie.ai"
    caption = (
        f"<b>Ауф · {escape(request.model.display_name)}</b>\n"
        f"Провайдер: <b>{provider}</b>\n"
        f"Качество: <b>{escape(request.resolution)}</b>\n"
        f"Референсов: <b>{len(request.references)}</b>\n"
        f"Задача провайдера: <code>{escape(record.task_id)}</code>"
    )
    try:
        if not record.result_urls:
            await self._bot.send_message(
                chat_id,
                caption + f"\n\n{provider} завершил задачу без URL результата.",
            )
            return
        for index, url in enumerate(record.result_urls):
            item_caption = caption if index == 0 else None
            if request.model.is_video:
                await self._bot.send_video(
                    chat_id,
                    video=url,
                    caption=item_caption,
                )
            else:
                await self._bot.send_photo(
                    chat_id,
                    photo=url,
                    caption=item_caption,
                )
    except TelegramAPIError:
        return


def install_auf_grs_brand() -> None:
    """Make every active media worker use canonical Auf presentation text."""

    global _INSTALLED
    if _INSTALLED:
        return

    # Old closures still read the historical global name, so point that transport
    # bridge at the canonical implementation while all active methods use Auf names.
    grs_resilience._sanitize_meow_text = _sanitize_auf_text
    grs_resilience._sanitize_auf_text = _sanitize_auf_text
    grs_resilience.ResilientFriendlyKieGenerationWorker._friendly_progress_text = (  # type: ignore[method-assign]
        _friendly_progress_text_auf
    )
    BaseKieGenerationWorker._deliver_best_effort = _deliver_best_effort_auf  # type: ignore[method-assign]
    grs_resilience.ResilientFriendlyKieGenerationWorker._deliver_best_effort = (  # type: ignore[method-assign]
        _deliver_best_effort_auf
    )
    CampaignGrsGenerationWorker._deliver_best_effort = _deliver_best_effort_auf  # type: ignore[method-assign]
    _INSTALLED = True


__all__ = ("install_auf_grs_brand",)
