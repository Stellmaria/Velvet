from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, ForceReply, Message

from velvet_bot.ai_job_runtime import AIJobTracker
from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.infrastructure.pose_extractor import PoseExtractorClient
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.presentation.telegram.routers.quality_operations_controllers.velvet_ai_image_prompt import (
    _comparison_models,
    _download_image,
    _message_image,
    _split_preformatted,
)
from velvet_bot.quality_ui import QualityCallback

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_POSE_EXTRACTOR_MARKER = "VELVET_AI:POSE_EXTRACTOR"


class PoseExtractorReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        source = reply.text or reply.caption or ""
        return _POSE_EXTRACTOR_MARKER in source


def _result_text(
    job_id: int,
    poses: dict[str, str],
    errors: dict[str, str],
) -> str:
    lines = [
        "<b>🧍 Qwen · извлечение позы</b>",
        "",
        f"Задание: <b>#{job_id}</b>",
        f"Готово моделей: <b>{len(poses)}</b>",
    ]
    for model, pose in poses.items():
        preview = escape(pose[:900].rstrip())
        if len(pose) > 900:
            preview += "\n\n…полная карта позы отправлена сообщениями в чат."
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
    poses: dict[str, str],
    errors: dict[str, str],
) -> str:
    completed = len(poses)
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
        f"<b>{icon} Pose extractor #{job_id} {status}</b>",
        "",
        f"Готово моделей: <b>{completed} из {total_models}</b>",
        f"Ошибок: <b>{len(errors)}</b>",
    ]
    if poses:
        lines.extend(["", "Полные карты позы отправлены ниже моноширным текстом."])
    return "\n".join(lines)


async def _send_pose_messages(
    message: Message,
    poses: dict[str, str],
) -> None:
    total_models = len(poses)
    for model_index, (model, pose) in enumerate(poses.items(), start=1):
        chunks = _split_preformatted(pose)
        for part_index, chunk in enumerate(chunks, start=1):
            part_label = (
                f" · часть {part_index}/{len(chunks)}"
                if len(chunks) > 1
                else ""
            )
            await message.answer(
                f"<b>🧍 Поза · модель {model_index}/{total_models}{part_label}</b>\n"
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

    models = _comparison_models(settings.ai_vision_model)
    model_lines = "\n".join(f"• <code>{escape(model)}</code>" for model in models)
    mode_text = (
        "Две модели последовательно извлекут карты позы для сравнения."
        if len(models) > 1
        else "Qwen извлечёт одну техническую карту позы."
    )
    await callback.answer()
    await callback.message.answer(
        "<b>🧍 Изображение → поза</b>\n\n"
        "Ответьте на это сообщение фотографией или image-файлом. "
        "Экстрактор опишет только положение тел, конечностей, опоры, контакты, "
        "перекрытия и ракурс, без внешности, одежды и художественного оформления. "
        f"{mode_text}\n\n"
        f"<b>Модели:</b>\n{model_lines}\n\n"
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
        kind="pose_extraction",
        title=(
            "Изображение → поза · сравнение моделей"
            if len(models) > 1
            else "Изображение → поза"
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
        poses: dict[str, str] = {}
        errors: dict[str, str] = {}
        keep_alive: str | int = 0 if len(models) > 1 else "15m"

        await tracker.stage("analyzing")
        async with get_local_ai_lock():
            for model in models:
                client = PoseExtractorClient(
                    provider=settings.ai_vision_provider,
                    base_url=settings.ai_vision_base_url,
                    model=model,
                    api_key=settings.ai_vision_api_key,
                    timeout_seconds=settings.ai_vision_timeout_seconds,
                    keep_alive=keep_alive,
                )
                try:
                    poses[model] = await client.generate(image)
                except asyncio.CancelledError:
                    raise
                except Exception as error:  # p2-approved-boundary: compare-model-partial
                    logger.warning(
                        "Pose-extractor comparison model unavailable model=%s error=%s",
                        model,
                        str(error).strip()[:500] or type(error).__name__,
                    )
                    errors[model] = str(error).strip()[:1200] or "Неизвестная ошибка."

        if not poses:
            details = "; ".join(f"{model}: {error}" for model, error in errors.items())
            raise RuntimeError(details or "Ни одна модель не вернула карту позы.")

        result_text = _result_text(tracker.job_id, poses, errors)
        await tracker.ready(
            result_text=result_text,
            result_payload={
                "poses": poses,
                "errors": errors,
                "models": list(models),
            },
        )
        await message.answer(
            _completion_notice(
                tracker.job_id,
                total_models=len(models),
                poses=poses,
                errors=errors,
            )
        )
        await _send_pose_messages(message, poses)
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:  # p2-approved-boundary: compensate-pose-extraction-job
        logger.exception("Pose extraction failed job_id=%s", tracker.job_id)
        await tracker.error(error)


__all__ = (
    "PoseExtractorReplyFilter",
    "_completion_notice",
    "router",
)
