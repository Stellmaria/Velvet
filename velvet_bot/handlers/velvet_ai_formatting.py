from __future__ import annotations

import asyncio
import io
import logging
import re
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

from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.quality_ui import QualityCallback, quality_callback
from velvet_bot.velvet_formatting import (
    FormattingMode,
    VelvetFormattingClient,
    render_velvet_post,
)
from velvet_bot.velvet_formatting_reports import VelvetFormattingReportRepository

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_MARKER_RE = re.compile(r"VELVET_AI:FORMAT:(shell|short|full)")
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS = (1.0, 3.0)
_MODE_LABELS: dict[FormattingMode, str] = {
    "shell": "Только оформление",
    "short": "Короткая публикация",
    "full": "Полный Velvet Anatomy",
}


class FormattingReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> dict[str, str] | bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        source = reply.text or reply.caption or ""
        match = _MARKER_RE.search(source)
        if match is None:
            return False
        return {"formatting_mode": match.group(1)}


def _formatting_menu() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "<b>✨ Оформление Velvet Anatomy</b>\n\n"
        "Выберите объём готовой публикации. Исходный материал отправляется через "
        "подписанную форму, поэтому обычные сообщения бот не перехватывает.\n\n"
        "<b>Только оформление</b> — фирменная оболочка вокруг исходного текста.\n"
        "<b>Короткая публикация</b> — заголовок, техстрока, краткое описание, "
        "палитра и теги.\n"
        "<b>Полный Velvet Anatomy</b> — весь канонический промт по разделам."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1 · Только оформление",
                    callback_data=quality_callback("format_start", section="shell"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="2 · Короткая публикация",
                    callback_data=quality_callback("format_start", section="short"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="3 · Полный Velvet Anatomy",
                    callback_data=quality_callback("format_start", section="full"),
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
    return text, keyboard


def _result_keyboard(mode: FormattingMode) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔁 Повторить этот режим",
                    callback_data=quality_callback("format_start", section=mode),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✨ Другой режим",
                    callback_data=quality_callback("format_menu"),
                ),
                InlineKeyboardButton(
                    text="↩️ Velvet AI",
                    callback_data=quality_callback("ai_menu"),
                ),
            ],
        ]
    )


async def _download_text_document(bot: Bot, message: Message) -> str | None:
    document = message.document
    if document is None:
        return None
    file_name = (document.file_name or "").casefold()
    mime_type = (document.mime_type or "").casefold()
    if not (mime_type.startswith("text/") or file_name.endswith((".txt", ".md"))):
        return None

    errors: list[BaseException] = []
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            destination = io.BytesIO()
            await bot.download(
                document.file_id,
                destination=destination,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                seek=True,
            )
            raw = destination.getvalue()
            if len(raw) > 128_000:
                raise ValueError("Текстовый файл больше 128 КБ.")
            return raw.decode("utf-8-sig").strip()
        except asyncio.CancelledError:
            raise
        except UnicodeDecodeError as error:
            errors.append(error)
            break
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
        raise RuntimeError(f"Не удалось прочитать текстовый файл: {errors[-1]}")
    return None


async def _source_text(message: Message, bot: Bot) -> str:
    direct = (message.text or message.caption or "").strip()
    if direct:
        return direct
    document_text = await _download_text_document(bot, message)
    return (document_text or "").strip()


@router.callback_query(QualityCallback.filter(F.action == "format_menu"))
async def handle_formatting_menu(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    text, keyboard = _formatting_menu()
    try:
        await callback.message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "format_start"))
async def handle_formatting_start(
    callback: CallbackQuery,
    callback_data: QualityCallback,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    mode = callback_data.section
    if mode not in _MODE_LABELS:
        await callback.answer("Неизвестный режим оформления.", show_alert=True)
        return
    settings = load_settings()
    if not settings.ai_vision_enabled:
        await callback.answer("Локальный Qwen отключён в настройках бота.", show_alert=True)
        return
    await callback.answer()
    label = _MODE_LABELS[mode]
    await callback.message.answer(
        f"<b>✨ {escape(label)}</b>\n\n"
        "Ответьте на это сообщение исходным промтом, описанием сцены или заметками. "
        "Можно приложить UTF-8 файл .txt/.md.\n\n"
        f"<code>VELVET_AI:FORMAT:{mode}</code>",
        reply_markup=ForceReply(
            selective=True,
            input_field_placeholder="Вставьте исходный материал",
        ),
    )


@router.message(FormattingReplyFilter())
async def handle_formatting_reply(
    message: Message,
    formatting_mode: str,
    database: Database,
    bot: Bot,
) -> None:
    mode: FormattingMode = formatting_mode  # type: ignore[assignment]
    try:
        source = await _source_text(message, bot)
    except Exception as error:
        await message.answer(f"Не удалось прочитать материал: <code>{escape(str(error))}</code>")
        return
    if len(source) < 10:
        await message.answer("Исходный материал слишком короткий для оформления.")
        return
    if len(source) > 16_000:
        await message.answer("Исходный материал длиннее 16 000 символов. Сократите его.")
        return

    settings = load_settings()
    if not settings.ai_vision_enabled:
        await message.answer("Локальный Qwen отключён в настройках бота.")
        return

    status = await message.answer(
        f"<b>🧠 Qwen · {_MODE_LABELS[mode]}</b>\n\n"
        "Собираю фирменную структуру и проверяю лимит Telegram."
    )
    try:
        client = VelvetFormattingClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        async with get_local_ai_lock():
            payload = await client.format(mode, source)
        rendered = render_velvet_post(mode, source, payload)
        await VelvetFormattingReportRepository(database).save(
            mode=mode,
            source_text=source,
            provider=client.provider,
            model=client.model,
            payload=payload,
            rendered_text=rendered,
            created_by=message.from_user.id if message.from_user else None,
        )
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.exception("Velvet formatting failed mode=%s", mode)
        await status.edit_text(
            "<b>❌ Оформление не завершено</b>\n\n"
            f"<code>{escape(str(error))}</code>"
        )
        return

    await status.edit_text(rendered, reply_markup=_result_keyboard(mode))


__all__ = ("FormattingReplyFilter", "router")
