from __future__ import annotations

from html import escape

from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.presentation.telegram.routers import workspace_character_pickers
from velvet_bot.presentation.telegram.routers import workspace_owner_controls
from velvet_bot.presentation.telegram.routers import workspaces
from velvet_bot import workspace_ui

_applied = False


async def _character_card_text(*args, **kwargs) -> str:
    text = await _original_character_card_text(*args, **kwargs)
    result: list[str] = []
    for line in text.splitlines():
        if "Открыть промт" in line or line == "Промт не назначен.":
            continue
        result.append(line)
        if line == "<b>Алиасы</b>":
            result.append(
                "Алиас — дополнительное имя персонажа. Его можно использовать "
                "вместо основного имени при поиске и сохранении материалов."
            )
    while len(result) >= 2 and result[-1] == result[-2] == "":
        result.pop()
    return "\n".join(result)


def _character_card_keyboard(*args, **kwargs) -> InlineKeyboardMarkup:
    keyboard = _original_character_card_keyboard(*args, **kwargs)
    rows: list[list[InlineKeyboardButton]] = []
    for row in keyboard.inline_keyboard:
        filtered = [
            button
            for button in row
            if button.text not in {"📝 Промт", "📝 Ссылка на промт"}
        ]
        if filtered:
            rows.append(filtered)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _character_list_text(*args, **kwargs) -> str:
    return (
        _original_character_list_text(*args, **kwargs)
        .replace("ветку, промт и алиас", "ветку и алиас")
        .replace("ветку, промт, алиас", "ветку и алиас")
    )


def _workspace_home_text(
    workspace,
    *,
    public_enabled: bool,
    enabled_modules: int,
    allowed_modules: int,
) -> str:
    visibility = "🌐 публичный read-only" if public_enabled else "🔒 приватный"
    return (
        f"<b>{escape(workspace.name)}</b>\n\n"
        f"Статус архива: <b>{visibility}</b>\n"
        f"Модули: <b>{enabled_modules}/{allowed_modules}</b> включено\n"
    )


def _media_card_keyboard(*args, **kwargs) -> InlineKeyboardMarkup:
    keyboard = _original_media_card_keyboard(*args, **kwargs)
    help_row: list[InlineKeyboardButton] | None = None
    rows: list[list[InlineKeyboardButton]] = []
    for row in keyboard.inline_keyboard:
        normalized: list[InlineKeyboardButton] = []
        for button in row:
            if button.text in {"⚡ Быстрый watermark", "⚙️ Настроить watermark"}:
                normalized.append(
                    InlineKeyboardButton(
                        text="⚡ Быстрый watermark",
                        callback_data=button.callback_data,
                    )
                )
            else:
                normalized.append(button)
        if any(button.text == "❓ Что делают кнопки" for button in normalized):
            help_row = normalized
        else:
            rows.append(normalized)
    if help_row is not None:
        rows.insert(max(0, len(rows) - 1), help_row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_media_help(
    callback: CallbackQuery,
    *,
    workspace_id: int,
    page,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    text = (
        "<b>Справка по кнопкам материала</b>\n\n"
        "<b>Лайк / Личная отметка</b> — отмечает текущую работу. В приватном "
        "архиве это личная отметка владельца; в публичном учитывается обычный лайк.\n\n"
        "<b>Подписаться</b> — включает или отключает уведомления о новых материалах "
        "этого персонажа.\n\n"
        "<b>Скачать оригинал</b> — отправляет владельцу сохранённый исходный файл.\n\n"
        "<b>Быстрый watermark</b> — создаёт отдельную копию с текущим логотипом "
        "пространства и открывает настройки положения, прозрачности, размера и "
        "отступа. Оригинал не заменяется. Если логотип ещё не загружен, бот "
        "предложит открыть настройку watermark.\n\n"
        "<b>Отправить на доработку</b> — помещает работу в очередь проверки и "
        "временно скрывает её из публичной выдачи.\n\n"
        "<b>Скрыть из публичного / Вернуть в публичный</b> — меняет видимость "
        "конкретной работы, когда публичный архив включён.\n\n"
        "<b>Пометить +18</b> — ограничивает показ подписчиками подключённого канала "
        "+18. <b>Включить блюр</b> — закрывает превью предупреждением.\n\n"
        "<b>Доступ и скачивание</b> — задаёт, кто может скачать материал и какую "
        "версию бот выдаёт читателям.\n\n"
        "<b>Ветка</b> открывает тему персонажа. <b>Удалить</b> безвозвратно удаляет "
        "текущий материал. <b>Закрыть</b> закрывает карточку.\n\n"
        "Некоторые кнопки появляются только после включения публичного режима "
        "или подключения нужного канала."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ К материалу",
                    callback_data=workspace_owner_controls._archive_callback(
                        "show",
                        workspace_id=workspace_id,
                        character_id=page.character.id,
                        offset=page.offset,
                        media_id=page.media.id,
                    ),
                )
            ]
        ]
    )
    await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


def apply_workspace_ui_adjustments() -> None:
    global _applied
    if _applied:
        return
    _applied = True

    workspace_character_pickers._card_text = _character_card_text
    workspace_character_pickers._card_keyboard = _character_card_keyboard
    workspace_character_pickers._character_list_text = _character_list_text

    workspace_owner_controls._archive_navigation = _media_card_keyboard
    workspace_owner_controls._show_media_help = _show_media_help

    workspace_ui.format_workspace_home = _workspace_home_text
    workspace_owner_controls.format_workspace_home = _workspace_home_text
    workspaces.format_workspace_home = _workspace_home_text


_original_character_card_text = workspace_character_pickers._card_text
_original_character_card_keyboard = workspace_character_pickers._card_keyboard
_original_character_list_text = workspace_character_pickers._character_list_text
_original_media_card_keyboard = workspace_owner_controls._archive_navigation


__all__ = ("apply_workspace_ui_adjustments",)
