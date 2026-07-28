from __future__ import annotations

import asyncio
import io
import logging
import os
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramNetworkError
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, ForceReply, Message

from velvet_bot.ai_job_runtime import AIJobTracker
from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.pose_extractor import PoseExtractorClient
from velvet_bot.quality_ui import QualityCallback

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_POSE_EXTRACTOR_MARKER = "VELVET_AI:POSE_EXTRACTOR"
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS = (1.0, 3.0)
_PRE_BLOCK_CONTENT_LIMIT = 3200
_SPLIT_BACKTRACK_LIMIT = 600


class PoseExtractorReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        source = reply.text or reply.caption or ""
        return _POSE_EXTRACTOR_MARKER in source


def _message_image(message: Message) -> tuple[str, str | None] | None:
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, photo.file_unique_id
    if message.document and (message.document.mime_type or "").startswith("image/"):
        return message.document.file_id, message.document.file_unique_id
    return None


def _pose_model(primary_model: str) -> str:
    return os.getenv("AI_POSE_MODEL", "").strip() or primary_model.strip()


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
            natural_cut = max(candidate.rfind("\n", floor), candidate.rfind(" ", floor))
            if natural_cut > 0:
                cut = natural_cut

        chunk = remaining[:cut].strip()
        if not chunk:
            chunk = remaining[:best]
            cut = best
        chunks.append(chunk)
        remaining = remaining[cut:].lstrip()
    return tuple(chunks)


def _result_text(job_id: int, model: str, pose: str) -> str:
    preview = escape(pose[:1200].rstrip())
    if len(pose) > 1200:
        preview += "\n\n…полный разбор отправлен сообщениями в чат."
    return (
        "<b>🦴 Qwen · экстрактор позы</b>\n\n"
        f"Задание: <b>#{job_id}</b>\n"
        f"Модель: <code>{escape(model)}</code>\n\n"
        f"<pre>{preview}</pre>"
    )[:4090]


async def _send_pose_messages(message: Message, model: str, pose: str) -> None:
    chunks = _split_preformatted(pose)
    for index, chunk in enumerate(chunks, start=1):
        part = f" · часть {index}/{len(chunks)}" if len(chunks) > 1 else ""
        await message.answer(
            f"<b>🦴 Точный разбор позы{part}</b>\n"
            f"<code>{escape(model)}</code>\n\n"
            f"<pre>{escape(chunk)}</pre>"
        )


@router.callback_query(QualityCallback.filter(F.action == "poseextract_start"))
async def handle_pose_extractor_start(callback: CallbackQuery) -> None:
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

    model = _pose_model(settings.ai_vision_model)
    await callback.answer()
    await callback.message.answer(
        "<b>🦴 Экстрактор позы</b>\n\n"
        "Ответьте на это сообщение фотографией или image-файлом. Бот опишет только "
        "геометрию: положение персонажей, головы, корпус, таз, каждую руку и ногу, "
        "касания, перекрытия, верёвки и другие предметы.\n\n"
        f"<b>Модель:</b> <code>{escape(model)}</code>\n\n"
        f"<code>{_POSE_EXTRACTOR_MARKER}</code>",
        reply_markup=ForceReply(selective=True),
    )


@router.message(PoseExtractorReplyFilter())
async def handle_pose_extractor_reply(
    message: Message,
    database: Database,
    bot: Bot,
) -> None:
    image_file = _message_image(message)
    if image_file is None:
        await message.answer(
            "Нужно ответить фотографией или image-документом, а не сообщением без изображения."
        )
        return

    settings = load_settings()
    if not settings.ai_vision_enabled:
        await message.answer("Локальный Qwen отключён в настройках бота.")
        return

    model = _pose_model(settings.ai_vision_model)
    file_id, file_unique_id = image_file
    tracker = await AIJobTracker.create(
        database=database,
        source_message=message,
        kind="pose_extraction",
        title="Точный экстрактор позы",
        provider=settings.ai_vision_provider,
        model=model,
        request_payload={
            "image_file_id": file_id,
            "image_file_unique_id": file_unique_id,
            "model": model,
        },
    )

    try:
        await tracker.stage("downloading")
        image = await _download_image(bot, file_id)
        await tracker.stage("analyzing")
        client = PoseExtractorClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        async with get_local_ai_lock():
            pose = await client.generate(image)

        await tracker.ready(
            result_text=_result_text(tracker.job_id, model, pose),
            result_payload={"pose": pose, "model": model},
        )
        await message.answer(
            f"<b>✅ Экстрактор позы #{tracker.job_id} завершён</b>\n\n"
            "Полный технический разбор отправлен ниже моноширным текстом."
        )
        await _send_pose_messages(message, model, pose)
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:  # p2-approved-boundary: compensate-pose-extractor-job
        logger.exception("Pose extraction failed job_id=%s", tracker.job_id)
        await tracker.error(error)
        await message.answer(
            f"<b>❌ Экстрактор позы #{tracker.job_id} не завершён</b>\n\n"
            f"<code>{escape(str(error).strip() or 'Неизвестная ошибка.')[:1500]}</code>"
        )


__all__ = (
    "PoseExtractorReplyFilter",
    "_pose_model",
    "_split_preformatted",
    "router",
)
