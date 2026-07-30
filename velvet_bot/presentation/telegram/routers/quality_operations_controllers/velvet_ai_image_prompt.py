from __future__ import annotations

from velvet_bot.presentation.telegram.shared import download_telegram_file

import asyncio
import io
import logging
import os
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, ForceReply, Message

from velvet_bot.ai_job_runtime import AIJobTracker
from velvet_bot.ai_vision import VisionAnalysisError
from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.infrastructure.image_to_prompt import ImageToPromptClient
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.quality_ui import QualityCallback

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_IMAGE_PROMPT_MARKER = "VELVET_AI:IMAGE_TO_PROMPT"
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS = (1.0, 3.0)
_PRE_BLOCK_CONTENT_LIMIT = 3200
_SPLIT_BACKTRACK_LIMIT = 600


class ImagePromptReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        source = reply.text or reply.caption or ""
        return _IMAGE_PROMPT_MARKER in source


def _message_image(message: Message) -> tuple[str, str | None] | None:
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, photo.file_unique_id
    if message.document and (message.document.mime_type or "").startswith("image/"):
        return message.document.file_id, message.document.file_unique_id
    return None


def _comparison_models(primary_model: str) -> tuple[str, ...]:
    primary = primary_model.strip()
    secondary = os.getenv("AI_VISION_COMPARE_MODEL", "").strip()
    if not secondary or secondary == primary:
        return (primary,)
    return primary, secondary


async def download_image(bot: Bot, file_id: str) -> bytes:
    return await download_telegram_file(
        bot,
        file_id,
        attempts=_DOWNLOAD_ATTEMPTS,
        timeout_seconds=_DOWNLOAD_TIMEOUT_SECONDS,
        retry_delays=_RETRY_DELAYS,
        failure_label="изображение",
        bad_request_type=TelegramBadRequest,
        network_error_types=(
            TelegramNetworkError,
            TimeoutError,
            ConnectionError,
            OSError,
        ),
        api_error_type=TelegramAPIError,
    )


_download_image = download_image


def _result_text(
    job_id: int,
    prompts: dict[str, str],
    errors: dict[str, str],
) -> str:
    lines = [
        "<b>🪄 Qwen · изображение в промт</b>",
        "",
        f"Задание: <b>#{job_id}</b>",
        f"Готово моделей: <b>{len(prompts)}</b>",
    ]
    for model, prompt in prompts.items():
        preview = escape(prompt[:900].rstrip())
        if len(prompt) > 900:
            preview += "\n\n…полная версия отправлена сообщениями в чат."
        lines.extend(
            [
                "",
                f"<b>Модель:</b> <code>{escape(model)}</code>",
                f"<pre>{preview}</pre>",
            ]
        )
    if errors:
        lines.extend(["", "<b>Не завершились:</b>"])
        for model, error in errors.items():
            lines.append(f"• <code>{escape(model)}</code>: {escape(error)[:400]}")
    return "\n".join(lines)[:4090]


def _completion_notice(
    job_id: int,
    *,
    total_models: int,
    prompts: dict[str, str],
    errors: dict[str, str],
) -> str:
    completed = len(prompts)
    if completed == total_models and not errors:
        icon = "✅"
        status = "завершён"
    elif completed:
        icon = "⚠️"
        status = "завершён частично"
    else:
        icon = "❌"
        status = "не выполнен"

    lines = [
        f"<b>{icon} Image-to-prompt #{job_id} {status}</b>",
        "",
        f"Готово моделей: <b>{completed} из {total_models}</b>",
        f"Ошибок: <b>{len(errors)}</b>",
    ]
    if prompts:
        lines.extend(["", "Полный результат отправлен ниже моноширным текстом."])
    return "\n".join(lines)


def _split_preformatted(
    value: str,
    *,
    max_escaped_length: int = _PRE_BLOCK_CONTENT_LIMIT,
) -> tuple[str, ...]:
    remaining = value.strip()
    if not remaining:
        return ("",)

    chunks: list[str] = []
    while remaining:
        low = 1
        high = len(remaining)
        best = 1
        while low <= high:
            middle = (low + high) // 2
            if len(escape(remaining[:middle])) <= max_escaped_length:
                best = middle
                low = middle + 1
            else:
                high = middle - 1

        cut = best
        if cut < len(remaining):
            candidate = remaining[:cut]
            floor = max(1, len(candidate) - _SPLIT_BACKTRACK_LIMIT)
            newline = candidate.rfind("\n", floor)
            space = candidate.rfind(" ", floor)
            natural_cut = max(newline, space)
            if natural_cut > 0:
                cut = natural_cut

        chunk = remaining[:cut].strip()
        if not chunk:
            chunk = remaining[:best]
            cut = best
        chunks.append(chunk)
        remaining = remaining[cut:].lstrip()

    return tuple(chunks)


async def _send_prompt_messages(
    message: Message,
    prompts: dict[str, str],
) -> None:
    total_models = len(prompts)
    for model_index, (model, prompt) in enumerate(prompts.items(), start=1):
        chunks = _split_preformatted(prompt)
        for part_index, chunk in enumerate(chunks, start=1):
            part_label = (
                f" · часть {part_index}/{len(chunks)}"
                if len(chunks) > 1
                else ""
            )
            await message.answer(
                f"<b>🧠 Модель {model_index}/{total_models}{part_label}</b>\n"
                f"<code>{escape(model)}</code>\n\n"
                f"<pre>{escape(chunk)}</pre>"
            )


@router.callback_query(QualityCallback.filter(F.action == "imageprompt_start"))
async def handle_image_prompt_start(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    settings = load_settings()
    if not settings.ai_vision_enabled:
        await callback.answer(
            "Локальный Qwen отключён в настройках бота.",
            show_alert=True,
        )
        return
    models = _comparison_models(settings.ai_vision_model)
    model_lines = "\n".join(f"• <code>{escape(model)}</code>" for model in models)
    mode_text = (
        "Две модели последовательно создадут версии промта для сравнения."
        if len(models) > 1
        else "Qwen создаст одну версию промта."
    )
    await callback.answer()
    await callback.message.answer(
        "<b>🪄 Изображение → промт</b>\n\n"
        "Ответьте на это сообщение фотографией или image-файлом. "
        f"{mode_text}\n\n"
        f"<b>Модели:</b>\n{model_lines}\n\n"
        f"<code>{_IMAGE_PROMPT_MARKER}</code>",
        reply_markup=ForceReply(selective=True),
    )


@router.message(ImagePromptReplyFilter())
async def handle_image_prompt_reply(
    message: Message,
    database: Database,
    bot: Bot,
) -> None:
    image_file = _message_image(message)
    if image_file is None:
        await message.answer(
            "Нужно ответить фотографией или image-документом, "
            "а не сообщением без изображения."
        )
        return

    settings = load_settings()
    if not settings.ai_vision_enabled:
        await message.answer("Локальный Qwen отключён в настройках бота.")
        return

    models = _comparison_models(settings.ai_vision_model)
    file_id, file_unique_id = image_file
    tracker = await AIJobTracker.create(
        database=database,
        source_message=message,
        kind="image_to_prompt",
        title=(
            "Изображение → промт · сравнение моделей"
            if len(models) > 1
            else "Изображение → промт"
        ),
        provider=settings.ai_vision_provider,
        model=" | ".join(models),
        request_payload={
            "image_file_id": file_id,
            "image_file_unique_id": file_unique_id,
            "models": list(models),
        },
    )
    try:
        await tracker.stage("downloading")
        image = await _download_image(bot, file_id)
        prompts: dict[str, str] = {}
        errors: dict[str, str] = {}
        failures: dict[str, BaseException] = {}
        keep_alive: str | int = 0 if len(models) > 1 else "15m"

        await tracker.stage("analyzing")
        async with get_local_ai_lock():
            for model in models:
                client = ImageToPromptClient(
                    provider=settings.ai_vision_provider,
                    base_url=settings.ai_vision_base_url,
                    model=model,
                    api_key=settings.ai_vision_api_key,
                    timeout_seconds=settings.ai_vision_timeout_seconds,
                    keep_alive=keep_alive,
                )
                try:
                    prompts[model] = await client.generate(image)
                except asyncio.CancelledError:
                    raise
                except Exception as error:  # p2-approved-boundary: compare-model-partial
                    log_model_failure = (
                        logger.info
                        if isinstance(error, VisionAnalysisError)
                        else logger.warning
                    )
                    log_model_failure(
                        "Image-to-prompt comparison model unavailable model=%s error=%s",
                        model,
                        str(error).strip()[:500] or type(error).__name__,
                    )
                    errors[model] = str(error).strip()[:1200] or "Неизвестная ошибка."
                    failures[model] = error

        if not prompts:
            details = "; ".join(f"{model}: {error}" for model, error in errors.items())
            failure_text = details or "Ни одна модель не вернула промт."
            if failures and all(
                isinstance(error, VisionAnalysisError) for error in failures.values()
            ):
                logger.warning(
                    "Image-to-prompt unavailable job_id=%s details=%s",
                    tracker.job_id,
                    failure_text[:1500],
                )
                await tracker.error(failure_text)
                await message.answer(
                    _completion_notice(
                        tracker.job_id,
                        total_models=len(models),
                        prompts=prompts,
                        errors=errors,
                    )
                )
                return
            raise RuntimeError(failure_text)

        result_text = _result_text(tracker.job_id, prompts, errors)
        await tracker.ready(
            result_text=result_text,
            result_payload={
                "prompts": prompts,
                "errors": errors,
                "models": list(models),
            },
        )
        await message.answer(
            _completion_notice(
                tracker.job_id,
                total_models=len(models),
                prompts=prompts,
                errors=errors,
            )
        )
        await _send_prompt_messages(message, prompts)
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:  # p2-approved-boundary: compensate-image-prompt-job
        logger.exception("Image-to-prompt failed job_id=%s", tracker.job_id)
        await tracker.error(error)


__all__ = (
    "ImagePromptReplyFilter",
    "_comparison_models",
    "_completion_notice",
    "_split_preformatted",
    "router",
)
