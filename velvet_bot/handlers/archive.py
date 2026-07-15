from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.database import Database
from velvet_bot.media import extract_image

router = Router(name=__name__)


@router.message(Command("save"))
async def handle_save_image(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Укажите имя персонажа после команды.\n\n"
            "Ответьте на изображение командой "
            "<code>/save@имя_бота Каин</code>."
        )
        return

    source_message = message.reply_to_message
    if source_message is None:
        await message.answer(
            "Команда должна быть отправлена ответом на изображение.\n\n"
            "Нажмите «Ответить» на фото или графический файл и отправьте "
            "<code>/save@имя_бота Каин</code>."
        )
        return

    media = extract_image(source_message)
    if media is None:
        await message.answer(
            "В сообщении, на которое вы ответили, нет поддерживаемого изображения.\n"
            "Сейчас принимаются фотографии и изображения, отправленные как файл."
        )
        return

    try:
        character = await database.get_character(command.args)
    except ValueError as error:
        await message.answer(escape(str(error)))
        return

    if character is None:
        await message.answer(
            "Такой персонаж не найден.\n\n"
            "Сначала создайте профиль: <code>/create Каин</code>."
        )
        return

    result = await database.save_character_media(
        character,
        media,
        saved_by=message.from_user.id if message.from_user else None,
        saved_in_chat=message.chat.id,
        source_chat_id=source_message.chat.id,
        source_message_id=source_message.message_id,
        source_thread_id=source_message.message_thread_id,
        command_message_id=message.message_id,
    )

    safe_character_name = escape(character.name)
    safe_storage_name = escape(result.storage_file_name)

    if not result.character_link_created:
        await message.answer(
            f"Это изображение уже находится в архиве персонажа "
            f"<b>{safe_character_name}</b>.\n"
            f"Файл: <code>{safe_storage_name}</code>"
        )
        return

    if result.media_created:
        status = "Новое изображение добавлено в архив."
    else:
        status = "Изображение уже было в общем архиве и привязано к персонажу."

    await message.answer(
        f"<b>{status}</b>\n\n"
        f"Персонаж: <b>{safe_character_name}</b>\n"
        f"Файл: <code>{safe_storage_name}</code>"
    )
