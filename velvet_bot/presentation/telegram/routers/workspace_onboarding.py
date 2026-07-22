from __future__ import annotations

from html import escape
from typing import cast

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.onboarding import (
    DESTINATION_SPECS,
    WORKSPACE_DESTINATION_KEYS,
    WorkspaceDestination,
    WorkspaceDestinationKey,
    WorkspaceOnboardingRepository,
    onboarding_readiness,
)
from velvet_bot.domains.workspaces.product_models import (
    GLOBAL_WORKSPACE_CREATOR_ID,
    WorkspaceModuleKey,
    WorkspaceModuleSetting,
)
from velvet_bot.domains.workspaces.product_service import (
    WorkspaceCreationAccessError,
    WorkspaceModuleAccessError,
    WorkspaceProductService,
)
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.workspace_ui import MODULE_HELP, MODULE_LABELS, WorkspaceForm

router = Router(name=__name__)


class WorkspaceOnboardingCallback(CallbackData, prefix="wob"):
    action: str
    workspace_id: int
    key: str = ""


def _callback(action: str, workspace_id: int, key: str = "") -> str:
    return WorkspaceOnboardingCallback(
        action=action,
        workspace_id=int(workspace_id),
        key=key,
    ).pack()


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


def _destination_key(value: str) -> WorkspaceDestinationKey | None:
    if value not in WORKSPACE_DESTINATION_KEYS:
        return None
    return cast(WorkspaceDestinationKey, value)


def _status_value(member) -> str:
    status = getattr(member, "status", "unknown")
    return str(getattr(status, "value", status))


def _chat_type_value(message: Message) -> str:
    value = message.chat.type
    return str(getattr(value, "value", value))


def _message_url(message: Message) -> str | None:
    username = getattr(message.chat, "username", None)
    if username:
        return f"https://t.me/{username}/{message.message_id}"
    chat_id = int(message.chat.id)
    raw = str(abs(chat_id))
    internal = raw[3:] if raw.startswith("100") else raw
    if message.chat.type in {ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL}:
        return f"https://t.me/c/{internal}/{message.message_id}"
    return None


def _topic_title(message: Message) -> str | None:
    thread_id = message.message_thread_id
    if thread_id is None:
        return None
    reply = message.reply_to_message
    created = getattr(reply, "forum_topic_created", None) if reply else None
    name = getattr(created, "name", None)
    return str(name)[:255] if name else f"Тема {thread_id}"


async def _edit_or_answer(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
) -> None:
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(
                text,
                reply_markup=reply_markup,
                disable_web_page_preview=True,
            )
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await callback.message.answer(
                    text,
                    reply_markup=reply_markup,
                    disable_web_page_preview=True,
                )
    await callback.answer()


async def _resolve_workspace(
    *,
    workspace_id: int,
    user_id: int,
    workspace_service: WorkspaceService,
    minimum_role: str = "admin",
) -> Workspace:
    global_owner = _is_global_owner(user_id)
    workspace = await workspace_service.set_active_workspace(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        global_owner=global_owner,
    )
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=int(user_id),
        minimum_role=cast(object, minimum_role),
        global_owner=global_owner,
    )
    if workspace.is_system:
        raise WorkspaceAccessError(
            "Системное пространство Velvet Anatomy не проходит пользовательский мастер."
        )
    return workspace


async def _active_workspace_from_command(
    *,
    message: Message,
    workspace_service: WorkspaceService,
    explicit_workspace_id: int | None = None,
) -> Workspace:
    user_id = message.from_user.id if message.from_user else 0
    global_owner = _is_global_owner(user_id)
    if explicit_workspace_id is not None:
        workspace = await workspace_service.set_active_workspace(
            workspace_id=explicit_workspace_id,
            user_id=user_id,
            global_owner=global_owner,
        )
    else:
        workspace = await workspace_service.resolve_active_workspace(
            user_id=user_id,
            global_owner=global_owner,
        )
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=user_id,
        minimum_role="admin",
        global_owner=global_owner,
    )
    if workspace.is_system:
        raise WorkspaceAccessError(
            "Сначала выберите личное пространство. Системный Velvet не настраивается этим мастером."
        )
    return workspace


async def _modules(
    *,
    workspace: Workspace,
    user_id: int,
    workspace_product_service: WorkspaceProductService,
) -> tuple[WorkspaceModuleSetting, ...]:
    return await workspace_product_service.list_modules(
        workspace_id=workspace.id,
        actor_user_id=user_id,
        global_owner=_is_global_owner(user_id),
    )


def _enabled_module_keys(
    modules: tuple[WorkspaceModuleSetting, ...],
) -> frozenset[WorkspaceModuleKey]:
    return frozenset(
        item.module_key
        for item in modules
        if item.is_allowed and item.is_enabled
    )


def _intro_text(workspace: Workspace, *, resumed: bool) -> str:
    prefix = "Настройка продолжена" if resumed else "Пространство создано"
    return (
        f"<b>🧭 {prefix}: {escape(workspace.name)}</b>\n\n"
        "Мастер проведёт по четырём шагам:\n"
        "1. покажет, как устроено пространство;\n"
        "2. даст выбрать разрешённые модули;\n"
        "3. привяжет реальные Telegram-чаты и темы;\n"
        "4. проверит, что включённым функциям есть куда сохранять данные.\n\n"
        "Архив остаётся приватным, пока вы отдельно не включите публичный режим. "
        "Настройку можно закрыть и продолжить командой <code>/workspace_setup</code>."
    )


def _intro_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📘 Как всё работает",
                    callback_data=_callback("guide", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧩 Шаг 2 · Выбрать модули",
                    callback_data=_callback("modules", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧭 Шаг 3 · Чаты и темы",
                    callback_data=_callback("destinations", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Проверить настройку",
                    callback_data=_callback("summary", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✖ Закрыть",
                    callback_data=_callback("close", workspace_id),
                )
            ],
        ]
    )


def _guide_text(workspace: Workspace) -> str:
    return (
        f"<b>📘 Как работает {escape(workspace.name)}</b>\n\n"
        "<b>Персонажи</b> — профили, имена, псевдонимы, категории, вселенные и истории.\n"
        "<b>Архив</b> — фото, видео и документы, изолированные от других пространств.\n"
        "<b>Референсы</b> — библиотека внешности и сравнения результатов.\n"
        "<b>Публикации</b> — черновики и отправка в выбранный канал.\n"
        "<b>Аналитика</b> — данные только подключённых каналов этого пространства.\n"
        "<b>Публичный архив</b> — отдельный read-only режим; сам по себе не включается.\n"
        "<b>Команда</b> — роли owner/admin/editor/reviewer/viewer.\n\n"
        "<b>Чаты и ветки</b>\n"
        "Бот не может безопасно угадывать, какой из ваших чатов считать архивом. "
        "Поэтому откройте нужный чат или конкретную тему и отправьте там команду "
        "<code>/workspace_bind НАЗНАЧЕНИЕ</code>. Для канала, где нельзя написать "
        "команду от себя, используйте в ЛС "
        "<code>/workspace_bind_channel НАЗНАЧЕНИЕ @channel</code>. Бот сохранит "
        "chat_id, текущую тему, ссылку и проверит свои права.\n\n"
        "Настройки всегда можно пересмотреть через <code>/workspace_setup</code>, "
        "а текущую схему — через <code>/workspace_setup_status</code>."
    )


def _guide_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=MODULE_LABELS[key],
                callback_data=_callback("modulehelp", workspace_id, key),
            )
        ]
        for key in MODULE_LABELS
    ]
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="✅ Гид понятен · к модулям",
                    callback_data=_callback("guidedone", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ В начало",
                    callback_data=_callback("intro", workspace_id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _modules_text(workspace: Workspace) -> str:
    return (
        f"<b>🧩 Модули · {escape(workspace.name)}</b>\n\n"
        "Нажмите на разрешённый модуль, чтобы включить или выключить его.\n"
        "✅ включён · ➖ выключен · ⛔ недоступен по выданному тарифу/разрешению.\n\n"
        "Мастер потребует назначение чата только для включённых функций. "
        "Персонажи и архив без места хранения считаются незавершённой настройкой."
    )


def _modules_keyboard(
    workspace_id: int,
    modules: tuple[WorkspaceModuleSetting, ...],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in modules:
        status = "⛔" if not item.is_allowed else ("✅" if item.is_enabled else "➖")
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {MODULE_LABELS[item.module_key]}"[:48],
                    callback_data=_callback("toggle", workspace_id, item.module_key),
                ),
                InlineKeyboardButton(
                    text="ℹ️",
                    callback_data=_callback("modulehelp", workspace_id, item.module_key),
                ),
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="✅ Модули выбраны",
                    callback_data=_callback("modulesdone", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ В начало",
                    callback_data=_callback("intro", workspace_id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _destination_location(destination: WorkspaceDestination) -> str:
    chat = destination.chat_title or str(destination.chat_id)
    if destination.message_thread_id is not None:
        return f"{chat} · {destination.topic_title or destination.message_thread_id}"
    return chat


def _destinations_text(
    workspace: Workspace,
    *,
    destinations: tuple[WorkspaceDestination, ...],
) -> str:
    configured = {item.destination_key: item for item in destinations}
    lines = [
        f"<b>🧭 Чаты и темы · {escape(workspace.name)}</b>",
        "",
        "Для каждой функции откройте нужный чат или тему и выполните указанную команду. "
        "Одна тема может использоваться для нескольких назначений.",
        "",
    ]
    for key in WORKSPACE_DESTINATION_KEYS:
        spec = DESTINATION_SPECS[key]
        item = configured.get(key)
        if item is None:
            lines.append(f"▫️ {spec.emoji} <b>{escape(spec.label)}</b> — не подключено")
        else:
            lines.append(
                f"✅ {spec.emoji} <b>{escape(spec.label)}</b> — "
                f"{escape(_destination_location(item))}"
            )
    lines.extend(
        [
            "",
            "Команда внутри нужной темы: <code>/workspace_bind characters</code> "
            "(замените characters на нужное назначение).",
        ]
    )
    return "\n".join(lines)


def _destinations_keyboard(
    workspace_id: int,
    destinations: tuple[WorkspaceDestination, ...],
) -> InlineKeyboardMarkup:
    configured = {item.destination_key for item in destinations}
    rows: list[list[InlineKeyboardButton]] = []
    for key in WORKSPACE_DESTINATION_KEYS:
        spec = DESTINATION_SPECS[key]
        status = "✅" if key in configured else "▫️"
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{status} {spec.emoji} {spec.label}"[:48],
                    callback_data=_callback("destinationhelp", workspace_id, key),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🔄 Обновить список",
                    callback_data=_callback("destinations", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Проверить готовность",
                    callback_data=_callback("summary", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К модулям",
                    callback_data=_callback("modules", workspace_id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _destination_help_text(workspace: Workspace, key: WorkspaceDestinationKey) -> str:
    spec = DESTINATION_SPECS[key]
    extra = (
        "Для форума бот должен быть администратором с правом управления темами."
        if spec.requires_forum_admin
        else "Бот проверит право публикации в выбранном чате."
    )
    return (
        f"<b>{spec.emoji} {escape(spec.label)} · {escape(workspace.name)}</b>\n\n"
        f"{escape(spec.description)}\n\n"
        "<b>Как подключить</b>\n"
        "1. Добавьте бота в нужный чат или канал.\n"
        "2. Откройте конкретную тему, если нужна именно ветка форума.\n"
        f"3. Отправьте там: <code>{escape(spec.command_hint)}</code>\n"
        "4. Вернитесь в мастер и нажмите «Обновить список».\n\n"
        f"{escape(extra)}"
    )


def _summary_keyboard(workspace_id: int, *, ready: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if ready:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚀 Завершить настройку",
                    callback_data=_callback("complete", workspace_id),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🧩 Изменить модули",
                    callback_data=_callback("modules", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧭 Изменить чаты и темы",
                    callback_data=_callback("destinations", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📘 Открыть гид",
                    callback_data=_callback("guide", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ В начало",
                    callback_data=_callback("intro", workspace_id),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _summary(
    *,
    workspace: Workspace,
    user_id: int,
    database: Database,
    workspace_product_service: WorkspaceProductService,
) -> tuple[str, bool]:
    repository = WorkspaceOnboardingRepository(database)
    state = await repository.get_state(workspace.id)
    if state is None:
        state = await repository.ensure_started(workspace_id=workspace.id, user_id=user_id)
    modules = await _modules(
        workspace=workspace,
        user_id=user_id,
        workspace_product_service=workspace_product_service,
    )
    enabled = _enabled_module_keys(modules)
    destinations = await repository.list_destinations(workspace.id)
    readiness = onboarding_readiness(
        modules_confirmed=state.modules_confirmed,
        guide_viewed=state.guide_viewed,
        enabled_modules=set(enabled),
        configured_destinations={item.destination_key for item in destinations},
    )
    lines = [
        f"<b>✅ Проверка · {escape(workspace.name)}</b>",
        "",
        f"Гид: {'✅ просмотрен' if state.guide_viewed else '❌ не просмотрен'}",
        f"Модули: {'✅ подтверждены' if state.modules_confirmed else '❌ не подтверждены'}",
        f"Включено модулей: <b>{len(enabled)}</b>",
        f"Подключено назначений: <b>{len(destinations)}</b>",
        "",
    ]
    if readiness.ready:
        lines.extend(
            [
                "<b>Пространство готово к работе.</b>",
                "Нажмите «Завершить настройку». После этого мастер останется доступен "
                "через /workspace_setup для любых изменений.",
            ]
        )
    else:
        lines.append("<b>Осталось:</b>")
        lines.extend(f"• {escape(item)}" for item in readiness.missing_steps)
    return "\n".join(lines), readiness.ready


@router.message(WorkspaceForm.waiting_workspace_name)
async def handle_workspace_name_and_start_wizard(
    message: Message,
    state: FSMContext,
    database: Database,
    workspace_product_service: WorkspaceProductService,
) -> None:
    user_id = message.from_user.id if message.from_user else 0
    name = (message.text or "").strip()
    try:
        workspace = await workspace_product_service.create_personal_workspace(
            owner_user_id=user_id,
            name=name,
        )
    except (ValueError, WorkspaceCreationAccessError) as error:
        await message.answer(str(error))
        return
    await state.clear()
    repository = WorkspaceOnboardingRepository(database)
    await repository.ensure_started(workspace_id=workspace.id, user_id=user_id)
    await message.answer(
        _intro_text(workspace, resumed=False),
        reply_markup=_intro_keyboard(workspace.id),
    )


@router.message(Command("workspace_setup"))
async def handle_workspace_setup(
    message: Message,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    if message.chat.type != ChatType.PRIVATE:
        await message.answer("Мастер настройки открывается в личных сообщениях бота.")
        return
    parts = (message.text or "").split()
    explicit_id = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    try:
        workspace = await _active_workspace_from_command(
            message=message,
            workspace_service=workspace_service,
            explicit_workspace_id=explicit_id,
        )
    except WorkspaceAccessError as error:
        await message.answer(str(error))
        return
    repository = WorkspaceOnboardingRepository(database)
    state = await repository.ensure_started(
        workspace_id=workspace.id,
        user_id=message.from_user.id if message.from_user else 0,
    )
    await message.answer(
        _intro_text(workspace, resumed=state.started_at is not None),
        reply_markup=_intro_keyboard(workspace.id),
    )


@router.message(Command("workspace_guide"))
async def handle_workspace_guide_command(
    message: Message,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    try:
        workspace = await _active_workspace_from_command(
            message=message,
            workspace_service=workspace_service,
        )
    except WorkspaceAccessError as error:
        await message.answer(str(error))
        return
    repository = WorkspaceOnboardingRepository(database)
    await repository.ensure_started(
        workspace_id=workspace.id,
        user_id=message.from_user.id if message.from_user else 0,
    )
    await repository.mark_guide_viewed(workspace.id)
    await message.answer(
        _guide_text(workspace),
        reply_markup=_guide_keyboard(workspace.id),
    )


@router.message(Command("workspace_setup_status"))
async def handle_workspace_setup_status(
    message: Message,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace = await _active_workspace_from_command(
            message=message,
            workspace_service=workspace_service,
        )
    except WorkspaceAccessError as error:
        await message.answer(str(error))
        return
    text, ready = await _summary(
        workspace=workspace,
        user_id=message.from_user.id if message.from_user else 0,
        database=database,
        workspace_product_service=workspace_product_service,
    )
    await message.answer(text, reply_markup=_summary_keyboard(workspace.id, ready=ready))


@router.message(Command("workspace_bind"))
async def handle_workspace_bind(
    message: Message,
    bot: Bot,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    if message.chat.type == ChatType.PRIVATE:
        await message.answer(
            "Эту команду нужно отправить внутри подключаемого чата, канала или темы."
        )
        return
    parts = (message.text or "").split()
    key = _destination_key(parts[1].casefold()) if len(parts) > 1 else None
    explicit_id = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
    if key is None:
        await message.answer(
            "Формат: <code>/workspace_bind НАЗНАЧЕНИЕ [WORKSPACE_ID]</code>\n"
            "Назначения: <code>" + ", ".join(WORKSPACE_DESTINATION_KEYS) + "</code>"
        )
        return
    try:
        workspace = await _active_workspace_from_command(
            message=message,
            workspace_service=workspace_service,
            explicit_workspace_id=explicit_id,
        )
    except WorkspaceAccessError as error:
        await message.answer(str(error))
        return
    user_id = message.from_user.id if message.from_user else 0
    modules = await _modules(
        workspace=workspace,
        user_id=user_id,
        workspace_product_service=workspace_product_service,
    )
    enabled = _enabled_module_keys(modules)
    spec = DESTINATION_SPECS[key]
    if spec.module_keys and not any(item in enabled for item in spec.module_keys):
        await message.answer(
            f"Сначала включите модуль для назначения «{escape(spec.label)}» "
            "в /workspace_setup."
        )
        return
    try:
        me = await bot.get_me()
        member = await bot.get_chat_member(message.chat.id, me.id)
    except TelegramAPIError as error:
        await message.answer(f"Не удалось проверить права бота: {escape(str(error))}")
        return
    status = _status_value(member)
    is_admin = status in {"administrator", "creator"}
    if not is_admin:
        await message.answer(
            "Бот должен быть администратором подключаемого чата или канала. "
            "После выдачи прав повторите команду."
        )
        return
    can_manage_topics = bool(getattr(member, "can_manage_topics", False))
    is_forum = bool(getattr(message.chat, "is_forum", False))
    if spec.requires_forum_admin and not is_forum:
        await message.answer(
            "Назначение «Персонажи» должно быть форумной супергруппой. "
            "Включите темы в настройках группы и повторите команду."
        )
        return
    if spec.requires_forum_admin and not can_manage_topics:
        await message.answer(
            "Для веток персонажей выдайте боту право «Управление темами» и повторите команду."
        )
        return
    can_post = bool(
        getattr(member, "can_post_messages", True)
        or getattr(member, "can_send_messages", True)
        or is_admin
    )
    if not can_post:
        await message.answer("У бота нет права отправлять сообщения в это назначение.")
        return
    repository = WorkspaceOnboardingRepository(database)
    await repository.ensure_started(workspace_id=workspace.id, user_id=user_id)
    try:
        destination = await repository.upsert_destination(
            workspace_id=workspace.id,
            destination_key=key,
            chat_id=message.chat.id,
            message_thread_id=(None if key == "characters" else message.message_thread_id),
            chat_type=_chat_type_value(message),
            chat_title=getattr(message.chat, "title", None),
            topic_title=(None if key == "characters" else _topic_title(message)),
            url=_message_url(message),
            bot_status=status,
            can_post=can_post,
            can_manage_topics=can_manage_topics,
            configured_by_user_id=user_id,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    if spec.channel_kind is not None:
        try:
            await workspace_service.configure_channel(
                workspace_id=workspace.id,
                actor_user_id=user_id,
                kind=spec.channel_kind,
                chat_id=message.chat.id,
                url=destination.url,
                global_owner=_is_global_owner(user_id),
            )
        except (ValueError, WorkspaceAccessError) as error:
            await repository.delete_destination(
                workspace_id=workspace.id,
                destination_key=key,
            )
            await message.answer(str(error))
            return
    thread = (
        f"\nТема: <code>{destination.message_thread_id}</code>"
        if destination.message_thread_id is not None
        else "\nТема: <b>основной чат</b>"
    )
    forum_note = (
        "\n⚠️ Чат не является форумом: отдельные ветки персонажей автоматически "
        "создаваться не смогут."
        if key == "characters" and not is_forum
        else ""
    )
    await message.answer(
        f"<b>✅ {escape(spec.label)} подключено</b>\n\n"
        f"Пространство: <b>{escape(workspace.name)}</b>\n"
        f"Chat ID: <code>{destination.chat_id}</code>"
        f"{thread}{forum_note}\n\n"
        "Вернитесь в ЛС бота и откройте /workspace_setup_status."
    )


@router.message(Command("workspace_unbind"))
async def handle_workspace_unbind(
    message: Message,
    database: Database,
    workspace_service: WorkspaceService,
) -> None:
    parts = (message.text or "").split()
    key = _destination_key(parts[1].casefold()) if len(parts) > 1 else None
    if key is None:
        await message.answer(
            "Формат: <code>/workspace_unbind НАЗНАЧЕНИЕ</code>\n"
            "Назначения: <code>" + ", ".join(WORKSPACE_DESTINATION_KEYS) + "</code>"
        )
        return
    try:
        workspace = await _active_workspace_from_command(
            message=message,
            workspace_service=workspace_service,
        )
    except WorkspaceAccessError as error:
        await message.answer(str(error))
        return
    changed = await WorkspaceOnboardingRepository(database).delete_destination(
        workspace_id=workspace.id,
        destination_key=key,
    )
    await message.answer(
        "Назначение удалено из мастера настройки."
        if changed
        else "Такое назначение не было подключено."
    )


@router.callback_query(WorkspaceOnboardingCallback.filter())
async def handle_workspace_onboarding_callback(
    callback: CallbackQuery,
    callback_data: WorkspaceOnboardingCallback,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    user_id = callback.from_user.id
    try:
        workspace = await _resolve_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=user_id,
            workspace_service=workspace_service,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return
    repository = WorkspaceOnboardingRepository(database)
    await repository.ensure_started(workspace_id=workspace.id, user_id=user_id)
    action = callback_data.action
    if action == "close":
        if isinstance(callback.message, Message):
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
        await callback.answer()
        return
    if action == "intro":
        state = await repository.get_state(workspace.id)
        await _edit_or_answer(
            callback,
            text=_intro_text(workspace, resumed=bool(state and state.started_at)),
            reply_markup=_intro_keyboard(workspace.id),
        )
        return
    if action == "guide":
        await repository.set_step(workspace_id=workspace.id, step="guide")
        await repository.mark_guide_viewed(workspace.id)
        await _edit_or_answer(
            callback,
            text=_guide_text(workspace),
            reply_markup=_guide_keyboard(workspace.id),
        )
        return
    if action == "guidedone":
        await repository.mark_guide_viewed(workspace.id)
        modules = await _modules(
            workspace=workspace,
            user_id=user_id,
            workspace_product_service=workspace_product_service,
        )
        await _edit_or_answer(
            callback,
            text=_modules_text(workspace),
            reply_markup=_modules_keyboard(workspace.id, modules),
        )
        return
    if action == "modulehelp":
        key = callback_data.key
        if key not in MODULE_HELP:
            await callback.answer("Неизвестный модуль.", show_alert=True)
            return
        await _edit_or_answer(
            callback,
            text=(
                f"<b>{escape(MODULE_LABELS[cast(WorkspaceModuleKey, key)])}</b>\n\n"
                f"{escape(MODULE_HELP[cast(WorkspaceModuleKey, key)])}"
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ К модулям",
                            callback_data=_callback("modules", workspace.id),
                        )
                    ]
                ]
            ),
        )
        return
    if action == "modules":
        await repository.set_step(workspace_id=workspace.id, step="modules")
        modules = await _modules(
            workspace=workspace,
            user_id=user_id,
            workspace_product_service=workspace_product_service,
        )
        await _edit_or_answer(
            callback,
            text=_modules_text(workspace),
            reply_markup=_modules_keyboard(workspace.id, modules),
        )
        return
    if action == "toggle":
        key = callback_data.key
        modules = await _modules(
            workspace=workspace,
            user_id=user_id,
            workspace_product_service=workspace_product_service,
        )
        current = next((item for item in modules if item.module_key == key), None)
        if current is None or not current.is_allowed:
            await callback.answer("Этот модуль не разрешён Стэл.", show_alert=True)
            return
        try:
            await workspace_product_service.set_module_enabled(
                workspace_id=workspace.id,
                actor_user_id=user_id,
                module_key=current.module_key,
                is_enabled=not current.is_enabled,
                global_owner=_is_global_owner(user_id),
            )
            if current.module_key == "public_archive" and current.is_enabled:
                await workspace_product_service.set_public_archive_enabled(
                    workspace_id=workspace.id,
                    actor_user_id=user_id,
                    enabled=False,
                    global_owner=_is_global_owner(user_id),
                )
        except (WorkspaceAccessError, WorkspaceModuleAccessError, ValueError) as error:
            await callback.answer(str(error), show_alert=True)
            return
        modules = await _modules(
            workspace=workspace,
            user_id=user_id,
            workspace_product_service=workspace_product_service,
        )
        await _edit_or_answer(
            callback,
            text=_modules_text(workspace),
            reply_markup=_modules_keyboard(workspace.id, modules),
        )
        return
    if action == "modulesdone":
        await repository.mark_modules_confirmed(workspace.id)
        destinations = await repository.list_destinations(workspace.id)
        await _edit_or_answer(
            callback,
            text=_destinations_text(workspace, destinations=destinations),
            reply_markup=_destinations_keyboard(workspace.id, destinations),
        )
        return
    if action == "destinations":
        await repository.set_step(workspace_id=workspace.id, step="destinations")
        destinations = await repository.list_destinations(workspace.id)
        await _edit_or_answer(
            callback,
            text=_destinations_text(workspace, destinations=destinations),
            reply_markup=_destinations_keyboard(workspace.id, destinations),
        )
        return
    if action == "destinationhelp":
        key = _destination_key(callback_data.key)
        if key is None:
            await callback.answer("Неизвестное назначение.", show_alert=True)
            return
        await _edit_or_answer(
            callback,
            text=_destination_help_text(workspace, key),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="↩️ К чатам и темам",
                            callback_data=_callback("destinations", workspace.id),
                        )
                    ]
                ]
            ),
        )
        return
    if action == "summary":
        await repository.set_step(workspace_id=workspace.id, step="summary")
        text, ready = await _summary(
            workspace=workspace,
            user_id=user_id,
            database=database,
            workspace_product_service=workspace_product_service,
        )
        await _edit_or_answer(
            callback,
            text=text,
            reply_markup=_summary_keyboard(workspace.id, ready=ready),
        )
        return
    if action == "complete":
        text, ready = await _summary(
            workspace=workspace,
            user_id=user_id,
            database=database,
            workspace_product_service=workspace_product_service,
        )
        if not ready:
            await _edit_or_answer(
                callback,
                text=text,
                reply_markup=_summary_keyboard(workspace.id, ready=False),
            )
            return
        await repository.complete(workspace_id=workspace.id, user_id=user_id)
        await _edit_or_answer(
            callback,
            text=(
                f"<b>🚀 {escape(workspace.name)} готово</b>\n\n"
                "Модули подтверждены, обязательные чаты и темы подключены, права бота "
                "проверены. Настройки можно менять через <code>/workspace_setup</code>, "
                "а схему смотреть через <code>/workspace_setup_status</code>."
            ),
            reply_markup=InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text="⚙️ Открыть настройки снова",
                            callback_data=_callback("intro", workspace.id),
                        )
                    ]
                ]
            ),
        )
        return
    await callback.answer("Неизвестное действие мастера.", show_alert=True)


__all__ = ("WorkspaceOnboardingCallback", "router")
