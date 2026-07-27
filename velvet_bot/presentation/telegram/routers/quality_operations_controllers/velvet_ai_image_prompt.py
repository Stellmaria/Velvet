from __future__ import annotations

import asyncio
import io
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)
from aiogram.filters import BaseFilter
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ForceReply,
    Message,
)

from velvet_bot.ai_job_runtime import AIJobTracker
from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.image_to_prompt import ImageToPromptClient
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.quality_ui import QualityCallback

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_IMAGE_PROMPT_MARKER = "VELVET_AI:IMAGE_TO_PROMPT"
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS = (1.0, 3.0)


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


async def _download_image(bot: Bot, file_id: str) -> bytes:
    errors: list[BaseException] = []
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            destination = io.BytesIO()
            await bot.download(
                file_id,
                destination=destination,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                seek=True,
            )
            value = destination.getvalue()
            if value:
                return value
            errors.append(RuntimeError("Telegram вернул пустой файл."))
        except asyncio.CancelledError:
            raise
        except TelegramBadRequest as error:
            errors.append(error)
            break
        except (TelegramNetworkError, TimeoutError, ConnectionError, OSError) as error:
            errors.append(error)
            if attempt >= _DOWNLOAD_ATTEMPTS:
                break
            await asyncio.sleep(_RETRY_DELAYS[attempt - 1])
        except TelegramAPIError as error:
            errors.append(error)
            break
    if errors:
        raise RuntimeError(f"Не удалось скачать изображение: {errors[-1]}")
    raise RuntimeError("Telegram вернул пустой файл.")


def _result_text(job_id: int, prompt: str) -> str:
    escaped = escape(prompt)
    if len(escaped) > 3400:
        escaped = escaped[:3400].rstrip() + "\n\n…полный текст приложен файлом."
    return (
        "<b>🪄 Qwen · изображение в промт</b>\n\n"
        f"Задание: <b>#{job_id}</b>\n\n"
        f"<pre>{escaped}</pre>"
    )[:4090]


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
    await callback.answer()
    await callback.message.answer(
        "<b>🪄 Изображение → промт</b>\n\n"
        "Ответьте на это сообщение фотографией или image-файлом. "
        "Qwen восстановит подробный основной промт, negative prompt, "
        "композицию, свет и цвет.\n\n"
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

    file_id, file_unique_id = image_file
    tracker = await AIJobTracker.create(
        database=database,
        source_message=message,
        kind="image_to_prompt",
        title="Изображение → промт",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        request_payload={
            "image_file_id": file_id,
            "image_file_unique_id": file_unique_id,
        },
    )
    try:
        await tracker.stage("downloading")
        image = await _download_image(bot, file_id)
        client = ImageToPromptClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        await tracker.stage("analyzing")
        async with get_local_ai_lock():
            prompt = await client.generate(image)
        await tracker.ready(
            result_text=_result_text(tracker.job_id, prompt),
            result_payload={"prompt": prompt},
        )
        await message.answer_document(
            BufferedInputFile(
                prompt.encode("utf-8"),
                filename=f"qwen-image-prompt-{tracker.job_id}.txt",
            ),
            caption="Полный image-to-prompt без ограничения длины сообщения Telegram",
        )
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:  # p2-approved-boundary: compensate-image-prompt-job
        logger.exception("Image-to-prompt failed job_id=%s", tracker.job_id)
        await tracker.error(error)


__all__ = ("ImagePromptReplyFilter", "router")
