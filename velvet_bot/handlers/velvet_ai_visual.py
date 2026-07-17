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
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.palette_composition_analysis import (
    CompositionAnalysisClient,
    PaletteMetrics,
    build_palette_card,
    extract_palette_metrics,
)
from velvet_bot.palette_composition_reports import PaletteCompositionReportRepository
from velvet_bot.quality_ui import QualityCallback, quality_callback

router = Router(name=__name__)
logger = logging.getLogger(__name__)

_MARKER = "VELVET_AI:VISUAL_ANALYSIS"
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS = (1.0, 3.0)


class VisualAnalysisReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        source = reply.text or reply.caption or ""
        return _MARKER in source


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
    for value in values[:8]:
        lines.append(f"• {escape(str(value))}")
    return lines


def _palette_line(metrics: PaletteMetrics) -> str:
    return " · ".join(
        f"<code>{color.hex_code}</code> {color.share:.1f}%"
        for color in metrics.colors
    ) or "—"


def _report_text(
    report_id: int,
    metrics: PaletteMetrics,
    report: dict[str, object],
) -> str:
    verdict = str(report.get("verdict") or "review")
    verdict_label = {
        "strong": "сильная композиция",
        "review": "нужна проверка",
        "weak": "композиция ослаблена",
        "insufficient": "недостаточно данных",
    }.get(verdict, verdict)
    verdict_emoji = {
        "strong": "✅",
        "review": "⚠️",
        "weak": "🚨",
        "insufficient": "🔎",
    }.get(verdict, "⚠️")
    pattern_label = {
        "centered": "центрированная",
        "rule_of_thirds": "правило третей",
        "diagonal": "диагональная",
        "symmetrical": "симметричная",
        "triangular": "треугольная",
        "layered": "многоплановая",
        "closeup": "крупный план",
        "mixed": "смешанная",
        "unclear": "не определена",
    }.get(str(report.get("composition_pattern") or "unclear"), "не определена")
    direction_label = {
        "front": "фронтальный",
        "side": "боковой",
        "back": "контровой",
        "top": "верхний",
        "bottom": "нижний",
        "mixed": "смешанный",
        "unclear": "не определён",
    }.get(str(report.get("lighting_direction") or "unclear"), "не определён")
    quality_label = {
        "soft": "мягкий",
        "hard": "жёсткий",
        "mixed": "смешанный",
        "unclear": "не определён",
    }.get(str(report.get("lighting_quality") or "unclear"), "не определён")
    crop_label = {
        "low": "низкий",
        "medium": "средний",
        "high": "высокий",
        "unclear": "не определён",
    }.get(str(report.get("crop_risk") or "unclear"), "не определён")
    temperature_label = {
        "warm": "тёплая",
        "cool": "холодная",
        "neutral": "нейтральная",
    }.get(metrics.temperature, metrics.temperature)

    lines = [
        f"<b>{verdict_emoji} Velvet AI · палитра и композиция</b>",
        "",
        f"Отчёт: <b>#{report_id}</b>",
        f"Размер: <b>{metrics.width} × {metrics.height}</b> · "
        f"соотношение <b>{metrics.aspect_ratio:.3f}</b>",
        f"Вердикт: <b>{escape(verdict_label)}</b>",
        f"Композиция: <b>{int(report.get('composition_score') or 0)} / 100</b> · "
        f"уверенность <b>{int(report.get('confidence') or 0)}%</b>",
        "",
        f"Схема: <b>{escape(pattern_label)}</b> · риск обрезания: <b>{escape(crop_label)}</b>",
        f"Баланс: <b>{int(report.get('balance_score') or 0)}</b> · "
        f"кадрирование: <b>{int(report.get('framing_score') or 0)}</b> · "
        f"иерархия: <b>{int(report.get('hierarchy_score') or 0)}</b>",
        f"Глубина: <b>{int(report.get('depth_score') or 0)}</b> · "
        f"свет: <b>{int(report.get('lighting_score') or 0)}</b> · "
        f"гармония палитры: <b>{int(report.get('palette_harmony_score') or 0)}</b>",
        "",
        f"Свет: <b>{escape(direction_label)}, {escape(quality_label)}</b>",
        f"Яркость: <b>{metrics.brightness}</b> · контраст: <b>{metrics.contrast}</b> · "
        f"насыщенность: <b>{metrics.saturation}</b>",
        f"Температура: <b>{escape(temperature_label)}</b>",
        f"Палитра: {_palette_line(metrics)}",
        "",
        f"<b>Итог:</b> {escape(str(report.get('summary_ru') or '—'))}",
        "",
        f"<b>Фокус:</b> {escape(str(report.get('focal_point_ru') or '—'))}",
        f"<b>Размещение:</b> {escape(str(report.get('subject_placement_ru') or '—'))}",
        f"<b>Обрезание:</b> {escape(str(report.get('crop_assessment_ru') or '—'))}",
        f"<b>Негативное пространство:</b> "
        f"{escape(str(report.get('negative_space_ru') or '—'))}",
        f"<b>Движение взгляда:</b> {escape(str(report.get('visual_flow_ru') or '—'))}",
        f"<b>Глубина:</b> {escape(str(report.get('depth_summary_ru') or '—'))}",
        f"<b>Световой разбор:</b> {escape(str(report.get('lighting_summary_ru') or '—'))}",
        f"<b>Цветовой разбор:</b> {escape(str(report.get('palette_summary_ru') or '—'))}",
    ]
    lines.extend(_list_block("Сильные стороны", report.get("strengths"), "✅"))
    lines.extend(_list_block("Проблемы", report.get("issues"), "⚠️"))
    lines.extend(_list_block("Практические исправления", report.get("recommendations"), "🛠"))
    return "\n".join(lines)[:4090]


def _report_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎨 Проверить другое изображение",
                    callback_data=quality_callback("visual_start"),
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


@router.callback_query(QualityCallback.filter(F.action == "visual_start"))
async def handle_visual_analysis_start(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    settings = load_settings()
    if not settings.ai_vision_enabled:
        await callback.answer("Локальный Qwen отключён в настройках бота.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        "<b>🎨 Палитра и композиция</b>\n\n"
        "Ответьте на это сообщение изображением как фото или image-файлом. "
        "Палитра будет измерена программно, а Qwen разберёт композицию, свет, "
        "иерархию, глубину и риск обрезаний.\n\n"
        f"<code>{_MARKER}</code>",
        reply_markup=ForceReply(selective=True),
    )


@router.message(VisualAnalysisReplyFilter())
async def handle_visual_analysis_reply(
    message: Message,
    database: Database,
    bot: Bot,
) -> None:
    result_file = _result_file(message)
    if result_file is None:
        await message.answer("Нужно ответить фотографией или image-документом.")
        return

    settings = load_settings()
    if not settings.ai_vision_enabled:
        await message.answer("Локальный Qwen отключён в настройках бота.")
        return

    status = await message.answer(
        "<b>🧠 Qwen анализирует композицию</b>\n\n"
        "Измеряю палитру и проверяю фокус, баланс, кадрирование, глубину и свет."
    )
    file_id, file_unique_id = result_file
    try:
        image = await _download_image(bot, file_id)
        metrics = await asyncio.to_thread(extract_palette_metrics, image)
        client = CompositionAnalysisClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=settings.ai_vision_api_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        async with get_local_ai_lock():
            report = await client.analyze_composition(image, metrics)
        report_id = await PaletteCompositionReportRepository(database).save(
            result_file_id=file_id,
            result_file_unique_id=file_unique_id,
            provider=client.provider,
            model=client.model,
            metrics=metrics,
            report=report,
            created_by=message.from_user.id if message.from_user else None,
        )
        palette_card = await asyncio.to_thread(build_palette_card, metrics)
    except asyncio.CancelledError:
        raise
    except Exception as error:
        logger.exception("Palette/composition analysis failed")
        await status.edit_text(
            "<b>❌ Анализ палитры и композиции не завершён</b>\n\n"
            f"<code>{escape(str(error))}</code>"
        )
        return

    await status.edit_text(
        _report_text(report_id, metrics, report),
        reply_markup=_report_keyboard(),
    )
    await message.answer_photo(
        BufferedInputFile(palette_card, filename=f"palette-{report_id}.png"),
        caption=(
            f"<b>Измеренная палитра · отчёт #{report_id}</b>\n"
            f"{_palette_line(metrics)}"
        ),
        protect_content=False,
    )


__all__ = ("VisualAnalysisReplyFilter", "router")
