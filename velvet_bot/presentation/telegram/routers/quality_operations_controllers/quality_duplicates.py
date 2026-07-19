from __future__ import annotations

from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.media_quality import (
    decide_duplicate_candidate,
    get_duplicate_candidate,
    list_duplicate_candidates,
)
from velvet_bot.media_sets import (
    create_set_candidate_from_duplicate,
    delete_duplicate_media,
)
from velvet_bot.quality_ui import (
    QualityCallback,
    build_duplicate_list,
    quality_callback,
)

router = Router(name=__name__)


async def _safe_edit(
    message: Message,
    text: str,
    keyboard: InlineKeyboardMarkup,
) -> None:
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


async def _send_preview(
    bot: Bot,
    chat_id: int,
    *,
    file_id: str,
    media_type: str,
    caption: str,
) -> None:
    try:
        if media_type == "photo":
            await bot.send_photo(
                chat_id=chat_id,
                photo=file_id,
                caption=caption,
                protect_content=True,
            )
        else:
            await bot.send_document(
                chat_id=chat_id,
                document=file_id,
                caption=caption,
                protect_content=True,
            )
    except TelegramAPIError:
        await bot.send_message(
            chat_id,
            f"{caption}\n\nФайл сейчас недоступен в Telegram.",
        )


async def show_duplicate_list(
    message: Message,
    database: Database,
    *,
    status: str,
    page_number: int,
) -> None:
    page = await list_duplicate_candidates(
        database,
        status=status,
        page=page_number,
    )
    text, keyboard = build_duplicate_list(page, status=status)
    await _safe_edit(message, text, keyboard)


def _comparison_keyboard(candidate_id: int, *, page: int, status: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Это дубль",
                    callback_data=quality_callback(
                        "dupconfirm",
                        section=status,
                        page=page,
                        item_id=candidate_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="🎞 Один сет",
                    callback_data=quality_callback(
                        "dupset",
                        section=status,
                        page=page,
                        item_id=candidate_id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🚫 Разные изображения",
                    callback_data=quality_callback(
                        "decide",
                        section="ignored",
                        page=page,
                        item_id=candidate_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К списку",
                    callback_data=quality_callback(
                        "duplicates",
                        section=status or "pending",
                        page=page,
                    ),
                )
            ],
        ]
    )


@router.callback_query(QualityCallback.filter(F.action == "duplicates"))
async def handle_duplicate_list(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await show_duplicate_list(
        callback.message,
        database,
        status=callback_data.section or "pending",
        page_number=callback_data.page,
    )
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "duplicate"))
async def handle_duplicate_open(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    bot: Bot,
) -> None:
    candidate = await get_duplicate_candidate(database, callback_data.item_id)
    if candidate is None or not isinstance(callback.message, Message):
        await callback.answer("Пара больше не найдена.", show_alert=True)
        return

    await _send_preview(
        bot,
        callback.message.chat.id,
        file_id=candidate.first_file_id,
        media_type=candidate.first_media_type,
        caption=(
            f"A · media #{candidate.first_media_id}\n"
            f"{candidate.first_file_name}\n"
            f"Персонажи: {', '.join(candidate.first_characters) or '—'}"
        ),
    )
    await _send_preview(
        bot,
        callback.message.chat.id,
        file_id=candidate.second_file_id,
        media_type=candidate.second_media_type,
        caption=(
            f"B · media #{candidate.second_media_id}\n"
            f"{candidate.second_file_name}\n"
            f"Персонажи: {', '.join(candidate.second_characters) or '—'}"
        ),
    )

    text = (
        "<b>Сравнение изображений</b>\n\n"
        f"Сходство: <b>{candidate.similarity_score}%</b>\n"
        f"Точные байты: <b>{'да' if candidate.exact_bytes else 'нет'}</b>\n"
        f"pHash: <b>{candidate.phash_distance}</b>\n"
        f"Центральный pHash: <b>{candidate.center_distance}</b>\n"
        f"dHash: <b>{candidate.dhash_distance}</b>\n"
        f"aHash: <b>{candidate.ahash_distance}</b>\n\n"
        "Если это дубль, бот предложит выбрать, какой файл оставить. "
        "Если это одна серия с разными персонажами, отправьте пару в медиасет."
    )
    await _safe_edit(
        callback.message,
        text,
        _comparison_keyboard(
            candidate.id,
            page=callback_data.page,
            status=callback_data.section or "pending",
        ),
    )
    await callback.answer("Оба файла отправлены выше.")


@router.callback_query(QualityCallback.filter(F.action == "dupconfirm"))
async def handle_duplicate_confirm_menu(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    candidate = await get_duplicate_candidate(database, callback_data.item_id)
    if candidate is None:
        await callback.answer("Пара больше не найдена.", show_alert=True)
        return
    text = (
        "<b>Это дубль. Какой файл оставить?</b>\n\n"
        f"A · media #{candidate.first_media_id}\n"
        f"Персонажи: {escape(', '.join(candidate.first_characters) or '—')}\n\n"
        f"B · media #{candidate.second_media_id}\n"
        f"Персонажи: {escape(', '.join(candidate.second_characters) or '—')}\n\n"
        "Удаление уберёт выбранный media-файл из всех персонажей, к которым он "
        "привязан, и удалит доступные копии из архивных веток Telegram."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить A",
                    callback_data=quality_callback(
                        "dupdelask",
                        section="first",
                        page=callback_data.page,
                        item_id=candidate.id,
                    ),
                ),
                InlineKeyboardButton(
                    text="🗑 Удалить B",
                    callback_data=quality_callback(
                        "dupdelask",
                        section="second",
                        page=callback_data.page,
                        item_id=candidate.id,
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="✅ Только отметить, не удалять",
                    callback_data=quality_callback(
                        "decide",
                        section="confirmed",
                        page=callback_data.page,
                        item_id=candidate.id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Назад",
                    callback_data=quality_callback(
                        "duplicate",
                        section=callback_data.section or "pending",
                        page=callback_data.page,
                        item_id=candidate.id,
                    ),
                )
            ],
        ]
    )
    await _safe_edit(callback.message, text, keyboard)
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "dupdelask"))
async def handle_duplicate_delete_confirmation(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    candidate = await get_duplicate_candidate(database, callback_data.item_id)
    if candidate is None:
        await callback.answer("Пара больше не найдена.", show_alert=True)
        return
    delete_first = callback_data.section == "first"
    media_id = candidate.first_media_id if delete_first else candidate.second_media_id
    file_name = candidate.first_file_name if delete_first else candidate.second_file_name
    characters = candidate.first_characters if delete_first else candidate.second_characters
    text = (
        "<b>Подтвердите удаление дубля</b>\n\n"
        f"media: <b>#{media_id}</b>\n"
        f"Файл: <code>{escape(file_name)}</code>\n"
        f"Будет удалён у персонажей: <b>{escape(', '.join(characters) or '—')}</b>\n\n"
        "Второй файл пары останется в базе. Действие необратимо."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Удалить выбранный дубль",
                    callback_data=quality_callback(
                        "dupdelete",
                        section=callback_data.section,
                        page=callback_data.page,
                        item_id=candidate.id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Отмена",
                    callback_data=quality_callback(
                        "dupconfirm",
                        section="pending",
                        page=callback_data.page,
                        item_id=candidate.id,
                    ),
                )
            ],
        ]
    )
    await _safe_edit(callback.message, text, keyboard)
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "dupdelete"))
async def handle_duplicate_delete(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    bot: Bot,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    candidate = await get_duplicate_candidate(database, callback_data.item_id)
    if candidate is None:
        await callback.answer("Пара больше не найдена.", show_alert=True)
        return
    media_id = (
        candidate.first_media_id
        if callback_data.section == "first"
        else candidate.second_media_id
    )
    try:
        deleted = await delete_duplicate_media(
            database,
            duplicate_candidate_id=candidate.id,
            media_id=media_id,
            decided_by=callback.from_user.id,
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    telegram_deleted = 0
    for reference in deleted.archive_messages:
        try:
            await bot.delete_message(reference.chat_id, reference.message_id)
            telegram_deleted += 1
        except TelegramAPIError:
            pass
    await callback.answer(
        (
            f"Дубль media #{deleted.media_id} удалён из базы. "
            f"Сообщений Telegram удалено: {telegram_deleted}."
        ),
        show_alert=True,
    )
    await show_duplicate_list(
        callback.message,
        database,
        status="pending",
        page_number=callback_data.page,
    )


@router.callback_query(QualityCallback.filter(F.action == "dupset"))
async def handle_duplicate_to_set(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    try:
        set_candidate_id = await create_set_candidate_from_duplicate(
            database,
            duplicate_candidate_id=callback_data.item_id,
            decided_by=callback.from_user.id,
        )
    except ValueError as error:
        await callback.answer(str(error), show_alert=True)
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎞 Выбрать фото и создать сет",
                    callback_data=quality_callback(
                        "set",
                        page=callback_data.page,
                        item_id=set_candidate_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К дублям",
                    callback_data=quality_callback(
                        "duplicates",
                        section="pending",
                        page=callback_data.page,
                    ),
                )
            ],
        ]
    )
    await _safe_edit(
        callback.message,
        (
            "<b>Пара больше не считается дублем.</b>\n\n"
            "Создано предложение медиасета. Откройте его, выберите нужные "
            "материалы и подтвердите объединение."
        ),
        keyboard,
    )
    await callback.answer("Пара перенесена в предложения сетов.")


@router.callback_query(QualityCallback.filter(F.action == "decide"))
async def handle_duplicate_decision(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    updated = await decide_duplicate_candidate(
        database,
        callback_data.item_id,
        status=callback_data.section,
        decided_by=callback.from_user.id,
    )
    await callback.answer(
        "Решение сохранено." if updated else "Пара больше не найдена.",
        show_alert=True,
    )
    await show_duplicate_list(
        callback.message,
        database,
        status="pending",
        page_number=callback_data.page,
    )
