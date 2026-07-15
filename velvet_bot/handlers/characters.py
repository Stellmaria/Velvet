from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from velvet_bot.database import Database

router = Router(name=__name__)


@router.message(Command("create", "crete"))
async def handle_create_character(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Укажите имя персонажа после команды.\n\n"
            "Пример: <code>/create Каин</code>"
        )
        return

    try:
        character, created = await database.create_character(
            command.args,
            created_by=message.from_user.id if message.from_user else None,
            created_in_chat=message.chat.id,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return

    safe_name = escape(character.name)
    if not created:
        await message.answer(
            f"Профиль <b>{safe_name}</b> уже существует.\n"
            f"ID персонажа: <code>{character.id}</code>\n\n"
            "Второй профиль с тем же именем не создан."
        )
        return

    await message.answer(
        "<b>Профиль персонажа создан</b>\n\n"
        f"Имя: <b>{safe_name}</b>\n"
        f"ID: <code>{character.id}</code>\n"
        "Изображений в архиве: <b>0</b>\n\n"
        "Следующим этапом к этому профилю можно будет сохранять изображения "
        "командой <code>/save Имя</code> в ответ на файл."
    )


@router.message(Command("characters"))
async def handle_list_characters(message: Message, database: Database) -> None:
    characters = await database.list_characters()
    if not characters:
        await message.answer(
            "Профилей персонажей пока нет.\n\n"
            "Создание: <code>/create Каин</code>"
        )
        return

    lines = ["<b>Персонажи Velvet Archive</b>", ""]
    lines.extend(
        f"{index}. <b>{escape(character.name)}</b> "
        f"<code>#{character.id}</code>"
        for index, character in enumerate(characters, start=1)
    )
    lines.append("")
    lines.append("Профиль: <code>/character Имя</code>")

    await message.answer("\n".join(lines))


@router.message(Command("character"))
async def handle_character(
    message: Message,
    command: CommandObject,
    database: Database,
) -> None:
    if not command.args:
        await message.answer(
            "Укажите имя персонажа.\n\n"
            "Пример: <code>/character Каин</code>"
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
            "Список: <code>/characters</code>"
        )
        return

    media_count = await database.count_character_media(character.id)
    await message.answer(
        "<b>Профиль персонажа</b>\n\n"
        f"Имя: <b>{escape(character.name)}</b>\n"
        f"ID: <code>{character.id}</code>\n"
        f"Изображений в архиве: <b>{media_count}</b>\n"
        f"Создан: <code>{escape(character.created_at)}</code>"
    )
