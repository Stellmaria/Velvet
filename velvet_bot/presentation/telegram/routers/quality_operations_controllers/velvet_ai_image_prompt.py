from __future__ import annotations

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


def _comparison_models(primary_model: str) -> tuple[str, ...]:
    primary = primary_model.strip()
    secondary = os.getenv("AI_VISION_COMPARE_MODEL", "").strip()
    if not secondary or secondary == primary:
        return (primary,)
    return primary, secondary


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
        preview = escape(prompt[:1200].rstrip())
        if len(prompt) > 1200:
            preview += "\n\n…полная версия приложена файлом."
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


def _result_document(prompts: dict[str, str], errors: dict[str, str]) -> str:
    sections: list[str] = []
    for index, (model, prompt) in enumerate(prompts.items(), start=1):
        sections.extend(
            [
                "=" * 80,
                f"МОДЕЛЬ {index}: {model}",
                "=" * 80,
                prompt.strip(),
                "",
            ]
        )
    if errors:
        sections.extend(["=" * 80, "ОШИБКИ МОДЕЛЕЙ", "=" * 80])
        for model, error in errors.items():
            sections.append(f"{model}: {error}")
    return "\n".join(sections).strip() + "\n"


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
                    logger.exception("Image-to-prompt model failed model=%s", model)
                    errors[model] = str(error).strip()[:1200] or "Неизвестная ошибка."

        if not prompts:
            details = "; ".join(f"{model}: {error}" for model, error in errors.items())
            raise RuntimeError(details or "Ни одна модель не вернула промт.")

        result_text = _result_text(tracker.job_id, prompts, errors)
        document = _result_document(prompts, errors)
        await tracker.ready(
            result_text=result_text,
            result_payload={
                "prompts": prompts,
                "errors": errors,
                "models": list(models),
            },
        )
        await message.answer_document(
            BufferedInputFile(
                document.encode("utf-8"),
                filename=f"qwen-image-prompts-{tracker.job_id}.txt",
            ),
            caption=(
                f"Image-to-prompt: готово {len(prompts)} из {len(models)} моделей."
            ),
        )
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:  # p2-approved-boundary: compensate-image-prompt-job
        logger.exception("Image-to-prompt failed job_id=%s", tracker.job_id)
        await tracker.error(error)


__all__ = (
    "ImagePromptReplyFilter",
    "_comparison_models",
    "router",
)
