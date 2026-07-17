from __future__ import annotations

import re
from html import escape

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

from velvet_bot.application.owner_profiles import rebuild_alias_index
from velvet_bot.application.owner_references import finish_reference_upload
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Database
from velvet_bot.owner_callbacks import (
    OwnerActionCallback,
    owner_action_callback,
    owner_callback,
)
from velvet_bot.presentation.telegram.owner_actions import (
    handle_owner_data_action,
    handle_owner_media_action,
    handle_owner_profile_action,
    handle_owner_reference_action,
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
        session = finish_reference_upload(
            reference_uploads,
            user_id=callback.from_user.id,
        )
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
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[_back_row("references")]
            ),
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
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[_back_row("aliases")]
            ),
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


__all__ = (
    "OwnerActionCallback",
    "OwnerActionReplyFilter",
    "router",
)
