from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.ai_quality import AIQualitySummary
from velvet_bot.domains.media_rework import MediaReworkSummary
from velvet_bot.owner_callbacks import owner_callback
from velvet_bot.quality_ui import quality_callback


def build_velvet_ai_menu(
    *,
    enabled: bool,
    provider: str,
    model: str,
    quality: AIQualitySummary,
    rework: MediaReworkSummary,
) -> tuple[str, InlineKeyboardMarkup]:
    state = "включён" if enabled else "отключён"
    text = (
        "<b>🤖 Qwen · работа с архивом</b>\n\n"
        f"Состояние: <b>{state}</b> · <code>{provider}:{model}</code>\n"
        f"Очередь: <b>{quality.pending + quality.processing}</b> · "
        f"готово <b>{quality.ready}</b> · ошибок <b>{quality.errors + quality.skipped}</b>\n"
        f"Без решения: <b>{quality.unreviewed}</b>\n"
        f"Доработка: <b>{rework.active}</b> · "
        f"Стэл <b>{rework.stel_priority}</b> · Qwen <b>{rework.qwen_only}</b>\n\n"
        "Все операции Qwen собраны здесь: архивная проверка, ручной анализ, "
        "референсы, промт, палитра, оформление, медиасеты, история и калибровка."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Проверка",
                    callback_data=quality_callback("quality_ops"),
                ),
                InlineKeyboardButton(
                    text=f"🛠 Доработка · {rework.active}",
                    callback_data=quality_callback("reworks"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text=f"📋 Отчёты · {quality.unreviewed}",
                    callback_data=quality_callback("qchecks", section="review"),
                ),
                InlineKeyboardButton(
                    text=f"❌ Ошибки · {quality.errors + quality.skipped}",
                    callback_data=quality_callback("qchecks", section="errors"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="▶️ Запуск",
                    callback_data=quality_callback("quality_run"),
                ),
                InlineKeyboardButton(
                    text="🕘 Последние",
                    callback_data=quality_callback("quality_recent"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔁 Повтор ошибок",
                    callback_data=quality_callback("quality_retry_errors"),
                ),
                InlineKeyboardButton(
                    text="🎛 Калибровка",
                    callback_data=quality_callback("qcal"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔎 Референс",
                    callback_data=quality_callback("refcompare_start"),
                ),
                InlineKeyboardButton(
                    text="📝 Промт ↔ фото",
                    callback_data=quality_callback("promptcheck_start"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎨 Палитра",
                    callback_data=quality_callback("visual_start"),
                ),
                InlineKeyboardButton(
                    text="✨ Оформление",
                    callback_data=quality_callback("format_menu"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🎞 Сеты",
                    callback_data=quality_callback("sets", section="pending"),
                ),
                InlineKeyboardButton(
                    text="🧠 Сет-проверка",
                    callback_data=quality_callback("setreports"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📋 История",
                    callback_data=quality_callback("aijobs"),
                ),
                InlineKeyboardButton(
                    text="🧬 Аудит",
                    callback_data=quality_callback("menu"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=quality_callback("ai_menu"),
                ),
                InlineKeyboardButton(
                    text="🏠 Главная",
                    callback_data=owner_callback("menu"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✖ Закрыть",
                    callback_data=quality_callback("close"),
                )
            ],
        ]
    )
    return text, keyboard


__all__ = ("build_velvet_ai_menu",)
