from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)
from aiogram.filters import BaseFilter
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.ai_job_runtime import AIJobTracker
from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.prompt_result_comparison import PromptResultComparisonClient
from velvet_bot.prompt_result_reports import PromptResultReportRepository
from velvet_bot.quality_ui import QualityCallback, quality_callback
from velvet_bot.velvet_ai_ui import build_velvet_ai_menu

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_PROMPT_TEXT_MARKER = "VELVET_AI:PROMPT_TEXT"
_PROMPT_IMAGE_MARKER = "VELVET_AI:PROMPT_IMAGE"
_SESSION_TTL = timedelta(minutes=30)
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS = (1.0, 3.0)


@dataclass(frozen=True, slots=True)
class PromptCheckSession:
    prompt_text: str
    created_at: datetime


_sessions: dict[tuple[int, int], PromptCheckSession] = {}


class PromptCheckReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> dict[str, str] | bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        source = reply.text or reply.caption or ""
        if _PROMPT_TEXT_MARKER in source:
            return {"prompt_check_stage": "text"}
        if _PROMPT_IMAGE_MARKER in source:
            return {"prompt_check_stage": "image"}
        return False


def _session_key(message: Message) -> tuple[int, int] | None:
    if message.from_user is None:
        return None
    return message.chat.id, message.from_user.id


def _session_is_alive(session: PromptCheckSession) -> bool:
    return datetime.now(UTC) - session.created_at <= _SESSION_TTL


def _result_file(message: Message) -> tuple[str, str | None] | None:
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


def _list_block(title: str, values: object, emoji: str) -> list[str]:
    if not isinstance(values, list) or not values:
        return []
    lines = ["", f"<b>{emoji} {escape(title)}</b>"]
    for value in values[:10]:
        lines.append(f"• {escape(str(value))}")
    return lines


def _report_text(report_id: int, report: dict[str, object]) -> str:
    verdict = str(report.get("verdict") or "partial")
    label = {
        "strong": "сильное соответствие",
        "partial": "частичное соответствие",
        "weak": "слабое соответствие",
        "insufficient": "недостаточно данных",
    }.get(verdict, verdict)
    emoji = {
        "strong": "✅",
        "partial": "⚠️",
        "weak": "🚨",
        "insufficient": "🔎",
    }.get(verdict, "⚠️")
    lines = [
        f"<b>{emoji} Velvet AI · промт против результата</b>",
        "",
        f"Отчёт: <b>#{report_id}</b>",
        f"Вердикт: <b>{escape(label)}</b>",
        f"Соответствие: <b>{int(report.get('overall_score') or 0)} / 100</b>",
        f"Уверенность Qwen: <b>{int(report.get('confidence') or 0)}%</b>",
        "",
        f"Персонажи и детали: <b>{int(report.get('subject_score') or 0)}</b> · "
        f"композиция: <b>{int(report.get('composition_score') or 0)}</b>",
        f"Свет: <b>{int(report.get('lighting_score') or 0)}</b> · "
        f"палитра: <b>{int(report.get('palette_score') or 0)}</b>",
        f"Окружение: <b>{int(report.get('environment_score') or 0)}</b> · "
        f"стиль: <b>{int(report.get('style_score') or 0)}</b> · "
        f"техника: <b>{int(report.get('technical_score') or 0)}</b>",
        "",
        f"<b>Итог:</b> {escape(str(report.get('summary_ru') or '—'))}",
    ]
    lines.extend(_list_block("Выполнено", report.get("matched_requirements"), "✅"))
    lines.extend(_list_block("Нарушено", report.get("violated_requirements"), "❌"))
    lines.extend(
        _list_block("Нельзя проверить надёжно", report.get("uncertain_requirements"), "🔎")
    )
    lines.extend(_list_block("Лишние элементы", report.get("extra_elements"), "➕"))
    lines.extend(_list_block("Что исправить сначала", report.get("priorities"), "🛠"))
    return "\n".join(lines)[:4090]


def _report_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📝 Проверить другой результат",
                    callback_data=quality_callback("promptcheck_start"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Velvet AI",
                    callback_data=quality_callback("ai_menu"),
                )
            ],
        ]
    )


async def _send_prompt_form(message: Message) -> None:
    await message.answer(
        "<b>📝 Промт против результата · шаг 1 из 2</b>\n\n"
        "Ответьте на это сообщение полным исходным промтом. После этого бот попросит "
        "готовое изображение.\n\n"
        f"<code>{_PROMPT_TEXT_MARKER}</code>",
        reply_markup=ForceReply(
            selective=True,
            input_field_placeholder="Вставьте исходный промт",
        ),
    )


async def _send_image_form(message: Message) -> None:
    await message.answer(
        "<b>🖼 Промт против результата · шаг 2 из 2</b>\n\n"
        "Ответьте на это сообщение готовым изображением как фото или image-файлом. "
        "Сохранённый промт действует 30 минут.\n\n"
        f"<code>{_PROMPT_IMAGE_MARKER}</code>",
        reply_markup=ForceReply(selective=True),
    )


@router.callback_query(QualityCallback.filter(F.action == "ai_menu"))
async def handle_velvet_ai_menu(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    settings = load_settings()
    text, keyboard = build_velvet_ai_menu(
        enabled=settings.ai_vision_enabled,
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
    )
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "promptcheck_start"))
async def handle_prompt_check_start(callback: CallbackQuery) -> None:
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
    await _send_prompt_form(callback.message)


@router.message(PromptCheckReplyFilter())
async def handle_prompt_check_reply(
    message: Message,
    prompt_check_stage: str,
    database: Database,
    bot: Bot,
) -> None:
    key = _session_key(message)
    if key is None:
        await message.answer("Не удалось определить пользователя формы.")
        return

    if prompt_check_stage == "text":
        prompt_text = " ".join((message.text or message.caption or "").split()).strip()
        if len(prompt_text) < 20:
            await message.answer(
                "Промт слишком короткий. Ответьте на форму полным техническим заданием."
            )
            return
        _sessions[key] = PromptCheckSession(
            prompt_text=prompt_text[:12000],
            created_at=datetime.now(UTC),
        )
        await _send_image_form(message)
        return

    session = _sessions.get(key)
    if session is None or not _session_is_alive(session):
        _sessions.pop(key, None)
        await message.answer(
            "Сохранённый промт отсутствует или устарел. Запустите проверку заново из Velvet AI."
        )
        return

    result_file = _result_file(message)
    if result_file is None:
        await message.answer(
            "Нужно ответить фотографией или image-документом, а не сообщением без изображения."
        )
        return

    settings = load_settings()
    if not settings.ai_vision_enabled:
        await message.answer("Локальный Qwen отключён в настройках бота.")
        return

    file_id, file_unique_id = result_file
    tracker = await AIJobTracker.create(
        database=database,
        source_message=message,
        kind="prompt_result",
        title="Промт против результата",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        request_payload={
            "result_file_id": file_id,
            "result_file_unique_id": file_unique_id,
            "prompt_length": len(session.prompt_text),
        },
    )
    try:
        await tracker.stage("downloading")
        image = await _download_image(bot, file_id)
        client = PromptResultComparisonClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        await tracker.stage("analyzing")
        async with get_local_ai_lock():
            report = await client.compare(session.prompt_text, image)
        await tracker.stage("saving")
        report_id = await PromptResultReportRepository(database).save(
            result_file_id=file_id,
            result_file_unique_id=file_unique_id,
            prompt_text=session.prompt_text,
            provider=client.provider,
            model=client.model,
            report=report,
            created_by=message.from_user.id if message.from_user else None,
        )
        rendered = _report_text(report_id, report)
        await tracker.ready(
            result_text=rendered,
            result_payload=report,
            reference_type="prompt_result_report",
            reference_id=report_id,
        )
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:  # p2-approved-boundary: compensate-prompt-result-job
        logger.exception("Prompt/result comparison failed job_id=%s", tracker.job_id)
        await tracker.error(error)
        return

    _sessions.pop(key, None)


__all__ = ("PromptCheckReplyFilter", "router")
