from __future__ import annotations

import re
from html import escape
from types import SimpleNamespace
from typing import Any

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Database
from velvet_bot.handlers.admin_directory import (
    handle_set_category,
    handle_set_prompt,
    handle_set_universe,
)
from velvet_bot.handlers.admin_stories import (
    handle_add_story,
    handle_set_story,
    handle_story_list,
)
from velvet_bot.handlers.archive import _handle_normal_save
from velvet_bot.handlers.character_aliases import (
    handle_alias_add,
    handle_alias_delete,
    handle_alias_list,
    handle_alias_reindex,
)
from velvet_bot.handlers.characters import (
    handle_bind_character_topic,
    handle_character,
    handle_create_character,
)
from velvet_bot.handlers.channel_analytics import handle_hashtag_stats
from velvet_bot.handlers.publication_center import handle_check_post
from velvet_bot.handlers.reference_management import handle_reference_delete_command
from velvet_bot.handlers.references import (
    handle_reference_upload_cancel,
    handle_reference_upload_done,
    handle_reference_upload_start,
    handle_show_references,
)
from velvet_bot.handlers.spoiler_save import handle_save_spoiler_media
from velvet_bot.handlers.telegram_analytics_import import (
    handle_discussion_stats,
    handle_import_channel,
    handle_import_discussion,
    handle_track_discussion,
)
from velvet_bot.owner_callbacks import (
    OwnerActionCallback,
    owner_action_callback,
    owner_callback,
)
from velvet_bot.reference_uploads import ReferenceUploadSessions

router = Router(name=__name__)

_OWNER_HOME = owner_callback("menu")
_MARKER_RE = re.compile(r"OWNER_ACTION:([a-z0-9_]+)")


def _cb(action: str) -> str:
    return owner_action_callback(action)


class OwnerActionReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> dict[str, str] | bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        marker_source = reply.text or reply.caption or ""
        match = _MARKER_RE.search(marker_source)
        if match is None:
            return False
        return {"owner_action": match.group(1)}


_FORM_COPY: dict[str, tuple[str, str, str]] = {
    "create": (
        "Создать персонажа",
        "Отправьте имя и при необходимости ссылку на тему.",
        "Аид https://t.me/c/3951213065/1398",
    ),
    "topic": (
        "Назначить тему архива",
        "Отправьте имя персонажа и ссылку на тему Telegram.",
        "Аид https://t.me/c/3951213065/1398",
    ),
    "character": (
        "Открыть карточку персонажа",
        "Отправьте имя персонажа.",
        "Аид",
    ),
    "category": (
        "Изменить пол или состав",
        "Отправьте имя персонажа и категорию: женский, мужской, мж, мжм, мм, жж или без.",
        "Аид мужской",
    ),
    "universe": (
        "Изменить вселенную",
        "Отправьте имя персонажа и вселенную: SHS, КР, ЛМ, ИДМ, BG3, Лагерта, Original или без.",
        "Аид КР",
    ),
    "story": (
        "Назначить историю",
        "Отправьте имя персонажа и сокращение истории либо «без».",
        "Аид СНР",
    ),
    "stories": (
        "Показать истории вселенной",
        "Отправьте название вселенной.",
        "КР",
    ),
    "storyadd": (
        "Добавить историю",
        "Отправьте вселенную, сокращение и полное название.",
        "КР СНР Секрет Небес: Реквием",
    ),
    "prompt": (
        "Привязать промт",
        "Отправьте имя персонажа и ссылку на Telegram-пост либо «off».",
        "Аид https://t.me/channel/123",
    ),
    "refadd": (
        "Начать загрузку референсов",
        "Отправьте имя персонажа. После запуска отправляйте фотографии обычными сообщениями.",
        "Аид",
    ),
    "refs": (
        "Показать референсы",
        "Отправьте имя персонажа.",
        "Аид",
    ),
    "refdel": (
        "Удалить референс",
        "Отправьте имя персонажа и номер референса.",
        "Аид 2",
    ),
    "aliasadd": (
        "Добавить алиас",
        "Отправьте имя персонажа и алиас без #.",
        "Каэль KaelLang",
    ),
    "aliases": (
        "Показать алиасы",
        "Отправьте имя персонажа.",
        "Каэль",
    ),
    "aliasdel": (
        "Удалить алиас",
        "Отправьте имя персонажа и алиас.",
        "Каэль KaelLang",
    ),
    "tagstats": (
        "Статистика хэштега",
        "Отправьте хэштег или имя тега.",
        "#Аид",
    ),
    "trackdiscussion": (
        "Подключить обсуждение",
        "Отправьте числовой Chat ID обсуждения.",
        "-1001234567890",
    ),
    "discussionstats": (
        "Статистика обсуждения",
        "Отправьте Chat ID либо слово «основной» для первого подключённого обсуждения.",
        "основной",
    ),
}

_MEDIA_FORMS: dict[str, tuple[str, str]] = {
    "save_media": (
        "Сохранить медиа в архив",
        "Ответьте на это сообщение фотографией, видео, анимацией или файлом. "
        "В подписи укажите только имя персонажа.",
    ),
    "save_spoiler": (
        "Сохранить медиа со спойлером",
        "Ответьте фотографией, видео, анимацией или файлом. В подписи укажите "
        "имя персонажа. Материал будет размыт в открытом архиве.",
    ),
    "check_post": (
        "Проверить публикацию",
        "Ответьте на это сообщение готовым текстом, медиа или пересланным постом. "
        "Бот создаст черновик и сразу откроет карточку проверки.",
    ),
    "import_channel": (
        "Импортировать канал",
        "Ответьте на это сообщение файлом result.json или ZIP экспорта Telegram.",
    ),
    "import_discussion": (
        "Импортировать обсуждение",
        "Ответьте файлом result.json или ZIP. При необходимости укажите Chat ID "
        "обсуждения в подписи к файлу.",
    ),
}


def _back_row(action: str = "menu") -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(text="↩️ Все действия", callback_data=_cb(action)),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data=_OWNER_HOME),
    ]


def _main_text() -> str:
    return (
        "<b>🧰 Все действия Velvet</b>\n\n"
        "Здесь собраны функции, которые раньше требовали отдельные slash-команды. "
        "Обычные панели открываются напрямую, а действия с параметрами запускают "
        "подписанную форму ответа."
    )


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Профили", callback_data=_cb("characters")),
                InlineKeyboardButton(text="🖼 Медиа и промты", callback_data=_cb("media")),
            ],
            [
                InlineKeyboardButton(text="🧷 Референсы", callback_data=_cb("references")),
                InlineKeyboardButton(text="#️⃣ Алиасы", callback_data=_cb("aliases")),
            ],
            [
                InlineKeyboardButton(text="📊 Данные и импорт", callback_data=_cb("data")),
                InlineKeyboardButton(text="📋 Карта команд", callback_data=_cb("map")),
            ],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data=_OWNER_HOME)],
        ]
    )


def _section_keyboard(section: str) -> InlineKeyboardMarkup:
    layouts: dict[str, list[list[tuple[str, str]]]] = {
        "characters": [
            [("➕ Создать", "form.create"), ("📁 Назначить тему", "form.topic")],
            [("👤 Открыть карточку", "form.character")],
            [("👥 Пол / состав", "form.category"), ("🎭 Вселенная", "form.universe")],
            [("📖 История", "form.story"), ("📚 Список историй", "form.stories")],
            [("➕ Добавить историю", "form.storyadd")],
        ],
        "media": [
            [("💾 Сохранить медиа", "media.save_media")],
            [("🌫 Сохранить со спойлером", "media.save_spoiler")],
            [("📝 Привязать промт", "form.prompt")],
            [("🧪 Проверить пост", "media.check_post")],
        ],
        "references": [
            [("➕ Начать загрузку", "form.refadd"), ("🖼 Показать", "form.refs")],
            [("🗑 Удалить по номеру", "form.refdel")],
            [("✅ Завершить загрузку", "direct.refdone"), ("✖ Отменить", "direct.refcancel")],
        ],
        "aliases": [
            [("➕ Добавить", "form.aliasadd"), ("📋 Показать", "form.aliases")],
            [("🗑 Удалить", "form.aliasdel")],
            [("🔄 Пересобрать индекс", "ask.aliasreindex")],
        ],
        "data": [
            [("📥 Импорт канала", "media.import_channel")],
            [("💬 Импорт обсуждения", "media.import_discussion")],
            [("🔗 Подключить обсуждение", "form.trackdiscussion")],
            [("📊 Статистика обсуждения", "form.discussionstats")],
            [("#️⃣ Статистика хэштега", "form.tagstats")],
        ],
    }
    rows = [
        [InlineKeyboardButton(text=label, callback_data=_cb(action)) for label, action in row]
        for row in layouts[section]
    ]
    rows.append(_back_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _section_text(section: str) -> str:
    labels = {
        "characters": "👤 Профили и классификация",
        "media": "🖼 Медиа, промты и публикации",
        "references": "🧷 Референсы персонажей",
        "aliases": "#️⃣ Алиасы и индекс хэштегов",
        "data": "📊 Данные, обсуждения и импорт",
    }
    return f"<b>{labels[section]}</b>\n\nВыберите действие."


def _map_text() -> str:
    return (
        "<b>📋 Карта переноса slash-команд</b>\n\n"
        "<b>Прямые панели:</b> system, health, version, analytics, channelstats, "
        "promptstats, characterstats, backup, quality, auditarchive, publish, "
        "characters, supervisor, logs, restart, update, rollback и Codex.\n\n"
        "<b>Формы:</b> create, topic, character, category, universe, story, "
        "stories, storyadd, prompt, refadd, refs, refdel, aliasadd, aliases, "
        "aliasdel, tagstats, trackdiscussion, discussionstats.\n\n"
        "<b>Контекстные формы:</b> save, save18, checkpost, importchannel, "
        "importdiscussion. В них файл или пост отправляется ответом на форму.\n\n"
        "<b>Отдельные кнопки:</b> refdone, refcancel, aliasreindex.\n\n"
        "Старые обработчики не удалены и остаются аварийным резервом, но для "
        "обычной работы ввод символа / больше не нужен."
    )


def _confirm_keyboard(action: str, label: str, *, back: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=label, callback_data=_cb(f"do.{action}")),
                InlineKeyboardButton(text="✖ Отмена", callback_data=_cb(back)),
            ]
        ]
    )


def _reference_session_message(callback: CallbackQuery) -> Message:
    assert isinstance(callback.message, Message)
    return callback.message.model_copy(
        update={"from_user": callback.from_user},
        deep=False,
    )


def _reference_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="↩️ Референсы", callback_data=_cb("references")),
                InlineKeyboardButton(text="🏠 Главное меню", callback_data=_OWNER_HOME),
            ]
        ]
    )


async def _safe_edit(message: Message, text: str, keyboard: InlineKeyboardMarkup) -> None:
    try:
        await message.edit_text(text, reply_markup=keyboard)
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).casefold():
            raise


async def _send_form(message: Message, action: str) -> None:
    title, instruction, placeholder = _FORM_COPY[action]
    await message.answer(
        f"<b>{escape(title)}</b>\n\n{escape(instruction)}\n\n"
        f"<code>OWNER_ACTION:{action}</code>",
        reply_markup=ForceReply(
            selective=True,
            input_field_placeholder=placeholder[:64],
        ),
    )


async def _send_media_form(message: Message, action: str) -> None:
    title, instruction = _MEDIA_FORMS[action]
    await message.answer(
        f"<b>{escape(title)}</b>\n\n{escape(instruction)}\n\n"
        f"<code>OWNER_ACTION:{action}</code>",
        reply_markup=ForceReply(selective=True),
    )


def _command(args: str | None) -> Any:
    return SimpleNamespace(args=args)


@router.callback_query(OwnerActionCallback.filter())
async def handle_owner_action_callback(
    callback: CallbackQuery,
    callback_data: OwnerActionCallback,
    reference_uploads: ReferenceUploadSessions,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    action = callback_data.action

    if action == "menu":
        await _safe_edit(callback.message, _main_text(), _main_keyboard())
    elif action in {"characters", "media", "references", "aliases", "data"}:
        await _safe_edit(
            callback.message,
            _section_text(action),
            _section_keyboard(action),
        )
    elif action == "map":
        await _safe_edit(
            callback.message,
            _map_text(),
            InlineKeyboardMarkup(inline_keyboard=[_back_row()]),
        )
    elif action.startswith("form."):
        await _send_form(callback.message, action.removeprefix("form."))
    elif action.startswith("media."):
        await _send_media_form(callback.message, action.removeprefix("media."))
    elif action in {"direct.refdone", "direct.refcancel"}:
        session_message = _reference_session_message(callback)
        if action == "direct.refdone":
            await handle_reference_upload_done(session_message, reference_uploads)
        else:
            await handle_reference_upload_cancel(session_message, reference_uploads)
        await session_message.answer(
            "Вернуться к управлению:",
            reply_markup=_reference_back_keyboard(),
        )
    elif action == "ask.aliasreindex":
        await _safe_edit(
            callback.message,
            "<b>Пересобрать индекс алиасов и связей хэштегов?</b>",
            _confirm_keyboard(
                "aliasreindex",
                "🔄 Пересобрать",
                back="aliases",
            ),
        )
    elif action == "do.aliasreindex":
        await handle_alias_reindex(callback.message, database)
        await callback.message.answer(
            "Вернуться к действиям:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back_row("aliases")]),
        )
    else:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return
    await callback.answer()


@router.message(OwnerActionReplyFilter())
async def handle_owner_action_reply(
    message: Message,
    owner_action: str,
    database: Database,
    bot: Bot,
    audit_logger: TelegramAuditLogger,
    reference_uploads: ReferenceUploadSessions,
    analytics_channel_ids: frozenset[int],
    publication_timezone: str = "Europe/Berlin",
) -> None:
    value = (message.text or message.caption or "").strip()
    if value.casefold() in {"отмена", "cancel"}:
        await message.answer(_main_text(), reply_markup=_main_keyboard())
        return

    if owner_action in {"save_media", "save_spoiler"}:
        if not value:
            await message.answer("Укажите имя персонажа в подписи к медиа.")
            return
        source = message.model_copy(deep=False)
        command_message = message.model_copy(
            update={"reply_to_message": source, "text": None, "caption": None},
            deep=False,
        )
        if owner_action == "save_spoiler":
            await handle_save_spoiler_media(
                command_message,
                _command(value),
                database,
                bot,
                audit_logger,
            )
        else:
            await _handle_normal_save(
                command_message,
                value,
                database,
                bot,
                audit_logger,
            )
        return

    if owner_action == "check_post":
        source = message.model_copy(deep=False)
        command_message = message.model_copy(
            update={"reply_to_message": source, "text": None, "caption": None},
            deep=False,
        )
        await handle_check_post(
            command_message,
            database,
            analytics_channel_ids,
            publication_timezone,
        )
        return

    if owner_action in {"import_channel", "import_discussion"}:
        source = message.model_copy(deep=False)
        command_message = message.model_copy(
            update={"reply_to_message": source, "text": None, "caption": None},
            deep=False,
        )
        command = _command(value if owner_action == "import_discussion" else None)
        if owner_action == "import_channel":
            await handle_import_channel(
                command_message,
                command,
                database,
                bot,
                analytics_channel_ids,
            )
        else:
            await handle_import_discussion(
                command_message,
                command,
                database,
                bot,
                analytics_channel_ids,
            )
        return

    handlers = {
        "create": lambda: handle_create_character(message, _command(value), database, bot),
        "topic": lambda: handle_bind_character_topic(message, _command(value), database, bot),
        "character": lambda: handle_character(message, _command(value), database),
        "category": lambda: handle_set_category(message, _command(value), database),
        "universe": lambda: handle_set_universe(message, _command(value), database),
        "story": lambda: handle_set_story(message, _command(value), database),
        "stories": lambda: handle_story_list(message, _command(value), database),
        "storyadd": lambda: handle_add_story(message, _command(value), database),
        "prompt": lambda: handle_set_prompt(message, _command(value), database),
        "refadd": lambda: handle_reference_upload_start(
            message,
            _command(value),
            database,
            reference_uploads,
            audit_logger,
        ),
        "refs": lambda: handle_show_references(message, _command(value), database, bot),
        "refdel": lambda: handle_reference_delete_command(
            message,
            _command(value),
            database,
            audit_logger,
        ),
        "aliasadd": lambda: handle_alias_add(message, _command(value), database),
        "aliases": lambda: handle_alias_list(message, _command(value), database),
        "aliasdel": lambda: handle_alias_delete(message, _command(value), database),
        "tagstats": lambda: handle_hashtag_stats(
            message,
            _command(value),
            database,
            analytics_channel_ids,
        ),
        "trackdiscussion": lambda: handle_track_discussion(
            message,
            _command(value),
            database,
            bot,
            analytics_channel_ids,
        ),
        "discussionstats": lambda: handle_discussion_stats(
            message,
            _command(None if value.casefold() == "основной" else value),
            database,
            analytics_channel_ids,
        ),
    }
    handler = handlers.get(owner_action)
    if handler is None:
        await message.answer("Неизвестная форма действия.", reply_markup=_main_keyboard())
        return
    await handler()


__all__ = (
    "OwnerActionCallback",
    "OwnerActionReplyFilter",
    "router",
)
