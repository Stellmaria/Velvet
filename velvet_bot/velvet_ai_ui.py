from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.handlers.admin_directory import AdminDirectoryCallback
from velvet_bot.owner_callbacks import owner_callback
from velvet_bot.quality_ui import quality_callback


def build_velvet_ai_menu(
    *,
    enabled: bool,
    provider: str,
    model: str,
) -> tuple[str, InlineKeyboardMarkup]:
    state = "включён" if enabled else "отключён"
    text = (
        "<b>🤖 Velvet AI</b>\n\n"
        f"Локальный анализ: <b>{state}</b>\n"
        f"Провайдер: <code>{provider}</code>\n"
        f"Модель: <code>{model}</code>\n\n"
        "Здесь собраны проверки изображения, референса, исходного промта, "
        "палитры, композиции, оформление публикаций и целостность медиасетов. "
        "Старые slash-команды сохранены как резервные, но нормальная работа "
        "выполняется кнопками."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🧠 Проверка качества",
                    callback_data=quality_callback("qchecks", section="review"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔎 Сравнение с референсом",
                    callback_data=AdminDirectoryCallback(action="categories").pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📝 Промт против результата",
                    callback_data=quality_callback("promptcheck_start"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎨 Палитра и композиция",
                    callback_data=quality_callback("visual_start"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✨ Оформление Velvet Anatomy",
                    callback_data=quality_callback("format_menu"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎞 Целостность медиасетов",
                    callback_data=quality_callback("setreports"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🎛 Калибровка модели",
                    callback_data=quality_callback("qcal"),
                ),
                InlineKeyboardButton(
                    text="🧬 Архивный аудит",
                    callback_data=quality_callback("menu"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=quality_callback("ai_menu"),
                ),
                InlineKeyboardButton(
                    text="↩️ Центр управления",
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
