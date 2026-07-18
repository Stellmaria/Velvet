from __future__ import annotations

import asyncio
import io
import json
import logging
from dataclasses import dataclass
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.ai_job_runtime import AIJobTracker
from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.quality_set_ai_repository import (
    MediaSetBundle,
    SetMediaItem,
    SetReportListItem,
    SetReportPage,
    _latest_report,
    _list_sets,
    _load_set,
    _save_report,
)
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.quality_ui import QualityCallback, quality_callback
from velvet_bot.set_consistency import SetConsistencyClient, SetConsistencyInput

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS = (1.0, 3.0)


async def _safe_edit(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup | None = None,
) -> None:
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


async def _download_item(bot: Bot, item: SetMediaItem) -> bytes:
    file_ids = [item.telegram_file_id]
    if item.preview_file_id and item.preview_file_id not in file_ids:
        file_ids.append(item.preview_file_id)
    errors: list[BaseException] = []
    for file_id in file_ids:
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
                break
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
        raise RuntimeError(
            f"Не удалось скачать media #{item.media_id}: {errors[-1]}"
        )
    raise RuntimeError(f"Telegram вернул пустой media #{item.media_id}.")


def _list_block(title: str, values: object, emoji: str) -> list[str]:
    if not isinstance(values, list) or not values:
        return []
    lines = ["", f"<b>{emoji} {escape(title)}</b>"]
    for value in values[:8]:
        lines.append(f"• {escape(str(value))}")
    return lines


def _format_report(
    bundle: MediaSetBundle,
    report_id: int,
    report: dict[str, object],
) -> str:
    verdict = str(report.get("verdict") or "review")
    label = {
        "coherent": "целостный сет",
        "review": "нужна ручная проверка",
        "incoherent": "целостность нарушена",
        "insufficient": "недостаточно данных",
    }.get(verdict, verdict)
    emoji = {
        "coherent": "✅",
        "review": "⚠️",
        "incoherent": "🚨",
        "insufficient": "🔎",
    }.get(verdict, "⚠️")

    lines = [
        f"<b>{emoji} Qwen · целостность сета #{bundle.id}</b>",
        "",
        f"Название: <b>{escape(bundle.title)}</b>",
        f"Отчёт: <b>#{report_id}</b>",
        f"Кадров: <b>{len(bundle.items)}</b>",
        f"Вердикт: <b>{escape(label)}</b>",
        f"Общая целостность: <b>{int(report.get('overall_score') or 0)} / 100</b>",
        f"Уверенность Qwen: <b>{int(report.get('confidence') or 0)}%</b>",
        "",
        f"Стиль: <b>{int(report.get('style_score') or 0)}</b> · "
        f"свет: <b>{int(report.get('lighting_score') or 0)}</b> · "
        f"палитра: <b>{int(report.get('palette_score') or 0)}</b>",
        f"Окружение: <b>{int(report.get('environment_score') or 0)}</b> · "
        f"композиция: <b>{int(report.get('composition_score') or 0)}</b>",
        f"Нарратив: <b>{int(report.get('narrative_score') or 0)}</b> · "
        f"персонажи: <b>{int(report.get('character_continuity_score') or 0)}</b> · "
        f"техника: <b>{int(report.get('technical_score') or 0)}</b>",
        "",
        f"<b>Итог:</b> {escape(str(report.get('summary_ru') or '—'))}",
    ]
    lines.extend(_list_block("Общие признаки", report.get("shared_traits"), "✅"))
    lines.extend(_list_block("Проблемы сета", report.get("set_issues"), "⚠️"))
    lines.extend(_list_block("Недостаточно видно", report.get("uncertain_areas"), "🔎"))

    raw_items = report.get("items")
    if isinstance(raw_items, list) and raw_items:
        lines.extend(["", "<b>Кадры:</b>"])
        ordered = sorted(
            (item for item in raw_items if isinstance(item, dict)),
            key=lambda item: (
                {"outlier": 0, "uncertain": 1, "core": 2}.get(
                    str(item.get("status")), 3
                ),
                int(item.get("index") or 0),
            ),
        )
        for item in ordered[:12]:
            status = str(item.get("status") or "uncertain")
            marker = {"core": "✅", "outlier": "🚨", "uncertain": "🔎"}.get(
                status, "🔎"
            )
            media_id = int(item.get("media_id") or 0)
            score = int(item.get("consistency_score") or 0)
            reasons = item.get("reasons")
            reason = ""
            if isinstance(reasons, list) and reasons:
                reason = " — " + escape(str(reasons[0]))
            lines.append(f"• {marker} media <b>#{media_id}</b>: <b>{score}/100</b>{reason}")

    return "\n".join(lines)[:4090]


def _detail_keyboard(set_id: int, *, page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 Проверить заново",
                    callback_data=quality_callback(
                        "setanalyze", page=page, item_id=set_id
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🖼 Показать материалы",
                    callback_data=quality_callback(
                        "setphotos", page=page, item_id=set_id
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К списку сетов",
                    callback_data=quality_callback("setreports", page=page),
                )
            ],
        ]
    )


async def _show_set_list(message: Message, database: Database, *, page: int) -> None:
    result = await _list_sets(database, page=page)
    lines = [
        "<b>🧠 Qwen · целостность медиасетов</b>",
        "",
        f"Сетов с двумя и более изображениями: <b>{result.total_items}</b>",
        f"Страница: <b>{result.page + 1}</b> из <b>{result.total_pages}</b>",
        "",
        "Qwen получает один компактный контакт-лист и проверяет стиль, свет, "
        "палитру, окружение, композицию, сюжетную связность и выбивающиеся кадры.",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for item in result.items:
        marker = {
            "coherent": "✅",
            "review": "⚠️",
            "incoherent": "🚨",
            "insufficient": "🔎",
        }.get(item.verdict, "🆕")
        score = f"{item.overall_score}%" if item.overall_score is not None else "не проверен"
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{marker} #{item.set_id} · {score} · "
                        f"{item.title[:30]} · {item.item_count} фото"
                    )[:64],
                    callback_data=quality_callback(
                        "setaudit", page=result.page, item_id=item.set_id
                    ),
                )
            ]
        )
    if result.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=quality_callback(
                        "setreports", page=(result.page - 1) % result.total_pages
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{result.page + 1} / {result.total_pages}",
                    callback_data=quality_callback("noop"),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=quality_callback(
                        "setreports", page=(result.page + 1) % result.total_pages
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=quality_callback("setreports", page=result.page),
            ),
            InlineKeyboardButton(
                text="↩️ К аудиту",
                callback_data=quality_callback("menu"),
            ),
        ]
    )
    await _safe_edit(
        message,
        "\n".join(lines),
        InlineKeyboardMarkup(inline_keyboard=rows),
    )


async def _show_set_detail(
    message: Message,
    database: Database,
    *,
    set_id: int,
    page: int,
) -> None:
    bundle = await _load_set(database, set_id)
    if bundle is None:
        await _safe_edit(
            message,
            "Сет больше не найден.",
            InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ К списку",
                            callback_data=quality_callback("setreports", page=page),
                        )
                    ]
                ]
            ),
        )
        return
    latest = await _latest_report(database, set_id)
    if latest is None:
        text = "\n".join(
            [
                f"<b>🆕 Сет #{bundle.id} ещё не проверен Qwen</b>",
                "",
                f"Название: <b>{escape(bundle.title)}</b>",
                f"Изображений: <b>{len(bundle.items)}</b>",
                "",
                "Проверка создаст контакт-лист и найдёт кадры, которые выбиваются "
                "по стилю, свету, палитре, окружению или качеству.",
            ]
        )
    else:
        report_id, report = latest
        text = _format_report(bundle, report_id, report)
    await _safe_edit(message, text, _detail_keyboard(bundle.id, page=page))


async def _analyze_set(
    database: Database,
    bot: Bot,
    *,
    set_id: int,
    created_by: int | None,
    tracker: AIJobTracker | None = None,
) -> tuple[MediaSetBundle, int, dict[str, object]]:
    bundle = await _load_set(database, set_id)
    if bundle is None:
        raise ValueError("Сет не найден.")
    if len(bundle.items) < 2:
        raise ValueError("В сете меньше двух доступных изображений.")
    if len(bundle.items) > 12:
        raise ValueError("Qwen проверяет не более 12 изображений за один сет.")

    settings = load_settings()
    if not settings.ai_vision_enabled:
        raise ValueError("Локальный Qwen отключён в настройках бота.")

    if tracker is not None:
        await tracker.stage("downloading")
    sources = await asyncio.gather(*(_download_item(bot, item) for item in bundle.items))
    inputs = tuple(
        SetConsistencyInput(
            media_id=item.media_id,
            image=source,
            characters=item.characters,
        )
        for item, source in zip(bundle.items, sources, strict=True)
    )
    client = SetConsistencyClient(
        provider=settings.ai_vision_provider,
        base_url=settings.ai_vision_base_url,
        model=settings.ai_vision_model,
        api_key=settings.ai_vision_api_key,
        timeout_seconds=settings.ai_vision_timeout_seconds,
    )
    if tracker is not None:
        await tracker.stage("analyzing")
    async with get_local_ai_lock():
        report = await client.analyze_set(inputs)
    if tracker is not None:
        await tracker.stage("saving")
    report_id = await _save_report(
        database,
        set_id=bundle.id,
        provider=client.provider,
        model=client.model,
        report=report,
        created_by=created_by,
    )
    return bundle, report_id, report


async def _send_set_media(bot: Bot, chat_id: int, bundle: MediaSetBundle) -> None:
    for item in bundle.items:
        caption = (
            f"Сет #{bundle.id} · media #{item.media_id}\n"
            f"Персонажи: {', '.join(item.characters) or '—'}"
        )
        try:
            if item.media_type == "photo":
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=item.telegram_file_id,
                    caption=caption,
                    protect_content=False,
                )
            else:
                await bot.send_document(
                    chat_id=chat_id,
                    document=item.telegram_file_id,
                    caption=caption,
                    protect_content=False,
                )
        except TelegramAPIError:
            await bot.send_message(chat_id, f"{caption}\nФайл сейчас недоступен.")


@router.callback_query(QualityCallback.filter(F.action == "setreports"))
async def handle_set_report_list(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await _show_set_list(callback.message, database, page=callback_data.page)
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "setaudit"))
async def handle_set_report_open(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await _show_set_detail(
        callback.message,
        database,
        set_id=callback_data.item_id,
        page=callback_data.page,
    )
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "setanalyze"))
async def handle_set_analyze(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    bot: Bot,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    settings = load_settings()
    if not settings.ai_vision_enabled:
        await callback.answer("Локальный Qwen отключён в настройках бота.", show_alert=True)
        return
    tracker = await AIJobTracker.create(
        database=database,
        source_message=callback.message,
        kind="media_set_consistency",
        title=f"Целостность медиасета #{callback_data.item_id}",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        request_payload={"set_id": callback_data.item_id},
    )
    await callback.answer(f"AI-задание #{tracker.job_id} зарегистрировано.")
    try:
        bundle, report_id, report = await _analyze_set(
            database,
            bot,
            set_id=callback_data.item_id,
            created_by=callback.from_user.id,
            tracker=tracker,
        )
        rendered = _format_report(bundle, report_id, report)
        await tracker.ready(
            result_text=rendered,
            result_payload=report,
            reference_type="media_set_consistency_report",
            reference_id=report_id,
        )
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:
        logger.exception(
            "Set consistency analysis failed set_id=%s job_id=%s",
            callback_data.item_id,
            tracker.job_id,
        )
        await tracker.error(error)
        await _safe_edit(
            callback.message,
            f"<b>❌ Проверка сета #{callback_data.item_id} не завершена</b>\n\n"
            f"AI-задание: <b>#{tracker.job_id}</b>\n"
            "Подробная причина сохранена в истории AI-заданий.",
            _detail_keyboard(callback_data.item_id, page=callback_data.page),
        )
        return
    await _safe_edit(
        callback.message,
        rendered,
        _detail_keyboard(bundle.id, page=callback_data.page),
    )


@router.callback_query(QualityCallback.filter(F.action == "setphotos"))
async def handle_set_photos(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    bot: Bot,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    bundle = await _load_set(database, callback_data.item_id)
    if bundle is None:
        await callback.answer("Сет больше не найден.", show_alert=True)
        return
    await callback.answer("Отправляю материалы отдельными сообщениями.")
    await _send_set_media(bot, callback.message.chat.id, bundle)


@router.message(Command("analyze_set", "qwen_set"))
async def handle_set_analysis_command(
    message: Message,
    command: CommandObject,
    database: Database,
    bot: Bot,
) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Проверка целостности сета доступна в личном чате с ботом.")
        return
    raw = " ".join((command.args or "").split()).strip()
    try:
        set_id = int(raw)
    except ValueError:
        await message.answer(
            "Укажите числовой ID сета.\n\n"
            "Пример: <code>/analyze_set 12</code>"
        )
        return
    if set_id <= 0:
        await message.answer("ID сета должен быть положительным числом.")
        return
    settings = load_settings()
    if not settings.ai_vision_enabled:
        await message.answer("Локальный Qwen отключён в настройках бота.")
        return
    tracker = await AIJobTracker.create(
        database=database,
        source_message=message,
        kind="media_set_consistency",
        title=f"Целостность медиасета #{set_id}",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        request_payload={"set_id": set_id, "source": "slash_command"},
    )
    try:
        bundle, report_id, report = await _analyze_set(
            database,
            bot,
            set_id=set_id,
            created_by=message.from_user.id if message.from_user else None,
            tracker=tracker,
        )
        rendered = _format_report(bundle, report_id, report)
        await tracker.ready(
            result_text=rendered,
            result_payload=report,
            reference_type="media_set_consistency_report",
            reference_id=report_id,
        )
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:
        logger.exception("Set consistency command failed set_id=%s job_id=%s", set_id, tracker.job_id)
        await tracker.error(error)


__all__ = ("router",)
