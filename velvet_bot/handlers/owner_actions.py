from __future__ import annotations

import re
from functools import partial
from html import escape

from aiogram import Bot, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import BaseFilter
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.application.owner_analytics import (
    DiscussionStats,
    ImportResult,
    load_discussion_stats,
    load_hashtag_stats,
    register_discussion,
)
from velvet_bot.application.owner_profiles import (
    add_alias_from_text,
    add_story_from_text,
    bind_character_topic,
    create_character_profile,
    delete_alias_from_text,
    list_aliases_from_text,
    list_stories_from_text,
    load_character_profile,
    rebuild_alias_index,
    set_category_from_text,
    set_prompt_from_text,
    set_story_from_text,
    set_universe_from_text,
)
from velvet_bot.application.owner_references import (
    delete_reference_by_index,
    finish_reference_upload,
    get_reference_page_by_name,
    start_reference_upload,
)
from velvet_bot.archive_ui import build_character_archive_keyboard
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.channel_analytics import HashtagStat
from velvet_bot.character_directory import category_label, universe_label
from velvet_bot.database import Character, Database
from velvet_bot.owner_callbacks import (
    OwnerActionCallback,
    owner_action_callback,
    owner_callback,
)
from velvet_bot.reference_ui import build_reference_keyboard, format_reference_caption
from velvet_bot.reference_uploads import ReferenceUploadSessions
from velvet_bot.services.media_save import save_media_from_message
from velvet_bot.services.telegram_exports import import_export_from_message
from velvet_bot.services.telegram_publications import create_publication_draft
from velvet_bot.services.telegram_topics import validate_topic_access
from velvet_bot.story_catalog import format_story_release, universe_requires_story
from velvet_bot.presentation.telegram.owner_actions import (
    handle_owner_data_action,
    handle_owner_media_action,
    handle_owner_profile_action,
    handle_owner_reference_action,
)

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
    "character": ("Открыть карточку персонажа", "Отправьте имя персонажа.", "Аид"),
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
    "stories": ("Показать истории вселенной", "Отправьте название вселенной.", "КР"),
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
    "refs": ("Показать референсы", "Отправьте имя персонажа.", "Аид"),
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
    "aliases": ("Показать алиасы", "Отправьте имя персонажа.", "Каэль"),
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
        "Ответьте фотографией, видео, анимацией или файлом. В подписи укажите имя персонажа.",
    ),
    "save_spoiler": (
        "Сохранить медиа со спойлером",
        "Ответьте фотографией, видео, анимацией или файлом. В подписи укажите имя персонажа.",
    ),
    "check_post": (
        "Проверить публикацию",
        "Ответьте готовым текстом, медиа или пересланным постом. Бот создаст черновик.",
    ),
    "import_channel": (
        "Импортировать канал",
        "Ответьте файлом result.json или ZIP экспорта Telegram.",
    ),
    "import_discussion": (
        "Импортировать обсуждение",
        "Ответьте файлом result.json или ZIP. Chat ID можно указать в подписи.",
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
        "Обычные панели открываются напрямую, а действия с параметрами запускают "
        "подписанную форму ответа. Slash-команды используют те же application use cases."
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
        "Профили, классификация, истории, алиасы, референсы и аналитические формы "
        "используют общий application-слой. Медиа, экспорт и публикации проходят "
        "через отдельные Telegram boundary services.\n\n"
        "Старые slash-маршруты сохранены как резервные адаптеры."
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


def _topic_line(character: Character) -> str:
    if not character.archive_topic_url:
        return "Тема архива: <b>не назначена</b>"
    return f'<a href="{escape(character.archive_topic_url, quote=True)}">Тема архива</a>'


async def _answer_profile(message: Message, profile, *, heading: str = "Профиль персонажа") -> None:
    character = profile.character
    created_at = character.created_at.astimezone().strftime("%d.%m.%Y %H:%M:%S %Z")
    await message.answer(
        f"<b>{heading}</b>\n\n"
        f"Имя: <b>{escape(character.name)}</b>\n"
        f"ID: <code>{character.id}</code>\n"
        f"Фото и видео в архиве: <b>{profile.media_count}</b>\n"
        f"Референсов: <b>{profile.reference_count}</b>\n"
        f"{_topic_line(character)}\n"
        f"Создан: <code>{escape(created_at)}</code>",
        reply_markup=build_character_archive_keyboard(character, profile.media_count),
    )


def _story_chunks(universe: str, stories) -> list[str]:
    header = (
        f"<b>Истории {escape(universe_label(universe))}</b>\n"
        "Сортировка: <b>от новых к старым</b>.\n\n"
    )
    chunks: list[str] = []
    current = header
    for story in stories:
        released = format_story_release(story.released_on, story.release_precision)
        prefix = "" if released == "дата не указана" else f"{released} · "
        line = f"• {prefix}<code>{escape(story.short_label)}</code> — {escape(story.title)}\n"
        if len(current) + len(line) > 3800:
            chunks.append(current.rstrip())
            current = header + line
        else:
            current += line
    chunks.append(current.rstrip())
    return chunks


def _format_date(value) -> str:
    return value.astimezone().strftime("%d.%m.%Y") if value else "—"


def _discussion_text(result: DiscussionStats) -> str:
    overview = result.overview
    participants = "\n".join(
        f"• <b>{escape(item.sender_name)}</b> — {item.message_count} сообщений, "
        f"ответов {item.reply_count}, медиа {item.media_count}"
        for item in result.participants
    ) or "• данных пока нет"
    hashtags = "\n".join(
        f"• <code>#{escape(item.hashtag)}</code> — {item.publication_count}"
        for item in result.hashtags
    ) or "• хэштегов пока нет"
    return (
        "<b>Статистика чата обсуждений</b>\n\n"
        f"Chat ID: <code>{result.chat_id}</code>\n"
        f"Период: <b>{_format_date(overview.first_message_at)}</b> — "
        f"<b>{_format_date(overview.last_message_at)}</b>\n"
        f"Сообщений: <b>{overview.total_messages}</b>\n"
        f"Публикаций / альбомов: <b>{overview.total_publications}</b>\n"
        f"Участников: <b>{overview.unique_participants}</b>\n"
        f"Ответов: <b>{overview.reply_messages}</b>\n"
        f"Медиа: <b>{overview.media_messages}</b>\n"
        f"Реакций: <b>{overview.total_reactions}</b>\n\n"
        f"<b>Активные участники</b>\n{participants}\n\n"
        f"<b>Частые хэштеги</b>\n{hashtags}"
    )


def _hashtag_text(item: HashtagStat) -> str:
    character = (
        f"\nПерсонаж в архиве: <b>{escape(item.character_name)}</b>"
        if item.character_name
        else "\nС карточкой персонажа пока не сопоставлен."
    )
    return (
        f"<b>#{escape(item.hashtag)}</b>\n\n"
        f"Публикаций: <b>{item.publication_count}</b>\n"
        f"Из них промтов: <b>{item.prompt_count}</b>\n"
        f"Последнее использование: <b>{_format_date(item.last_used_at)}</b>"
        f"{character}"
    )


def _import_text(result: ImportResult) -> str:
    summary = result.summary
    source_label = "канал" if summary.source_kind == "channel" else "обсуждение"
    duplicate = "\n\n⚠️ Этот файл уже импортировался ранее." if summary.duplicate_import else ""
    text = (
        f"<b>Импорт завершён: {source_label}</b>\n\n"
        f"Источник: <b>{escape(summary.source_name)}</b>\n"
        f"Chat ID: <code>{summary.source_chat_id}</code>\n"
        f"Записей: <b>{summary.total_records}</b>\n"
        f"Импортировано: <b>{summary.imported_messages}</b>\n"
        f"Публикаций / альбомов: <b>{summary.publication_count}</b>\n"
        f"Промтов: <b>{summary.prompt_publications}</b>\n"
        f"Хэштегов: <b>{summary.hashtag_count}</b>\n"
        f"Персонажей сопоставлено: <b>{summary.character_matches}</b>"
        f"{duplicate}"
    )
    if result.relink is not None:
        text += (
            "\n\n<b>Связка с публикациями</b>\n"
            f"Корней найдено: <b>{result.relink.roots_marked}</b>\n"
            f"Комментариев привязано: <b>{result.relink.comments_linked}</b>\n"
            f"Веток сопоставлено: <b>{result.relink.threads_linked}</b>"
        )
    return text


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
        await _safe_edit(callback.message, _section_text(action), _section_keyboard(action))
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
        session = finish_reference_upload(reference_uploads, user_id=callback.from_user.id)
        if session is None:
            text = "Активной загрузки референсов нет."
        elif action == "direct.refdone":
            text = (
                "<b>Загрузка завершена</b>\n\n"
                f"Персонаж: <b>{escape(session.character_name)}</b>\n"
                f"Добавлено за сеанс: <b>{session.added_count}</b>"
            )
        else:
            text = "Загрузка референсов остановлена."
        await callback.message.answer(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back_row("references")]),
        )
    elif action == "ask.aliasreindex":
        await _safe_edit(
            callback.message,
            "<b>Пересобрать индекс алиасов и связей хэштегов?</b>",
            _confirm_keyboard("aliasreindex", "🔄 Пересобрать", back="aliases"),
        )
    elif action == "do.aliasreindex":
        result = await rebuild_alias_index(database)
        await callback.message.answer(
            "<b>Индекс хэштегов пересобран.</b>\n\n"
            f"Новых основных алиасов: <b>{result.created_name_aliases}</b>\n"
            f"Распознано связей: <b>{result.matched_links}</b> из "
            f"<b>{result.total_hashtags}</b>.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back_row("aliases")]),
        )
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
    del publication_timezone
    value = (message.text or message.caption or "").strip()
    if value.casefold() in {"отмена", "cancel"}:
        await message.answer(_main_text(), reply_markup=_main_keyboard())
        return

    actor_id = message.from_user.id if message.from_user else None
    try:
        if await handle_owner_media_action(
            message=message,
            owner_action=owner_action,
            value=value,
            database=database,
            bot=bot,
            audit_logger=audit_logger,
            analytics_channel_ids=analytics_channel_ids,
            actor_id=actor_id,
        ):
            return
        if await handle_owner_profile_action(
            message=message,
            owner_action=owner_action,
            value=value,
            database=database,
            bot=bot,
            actor_id=actor_id,
        ):
            return
        if await handle_owner_reference_action(
            message=message,
            owner_action=owner_action,
            value=value,
            database=database,
            bot=bot,
            audit_logger=audit_logger,
            reference_uploads=reference_uploads,
            actor_id=actor_id,
        ):
            return
        if await handle_owner_data_action(
            message=message,
            owner_action=owner_action,
            value=value,
            database=database,
            bot=bot,
            analytics_channel_ids=analytics_channel_ids,
            actor_id=actor_id,
        ):
            return
        raise ValueError("Неизвестная форма действия.")
    except (ValueError, RuntimeError) as error:
        await message.answer(
            escape(str(error)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back_row()]),
        )
        raise ValueError("Неизвестная форма действия.")
    except (ValueError, RuntimeError) as error:
        await message.answer(
            escape(str(error)),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[_back_row()]),
        )


__all__ = (
    "OwnerActionCallback",
    "OwnerActionReplyFilter",
    "router",
)
