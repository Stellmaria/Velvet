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
        "Для обычного личного архива нужны три понятных шага:\n"
        "1. посмотреть короткий гид;\n"
        "2. выбрать доступные модули;\n"
        "3. один раз подключить основной форумный чат архива.\n\n"
        "После этого персонажи создаются кнопкой по имени: бот сам создаёт для "
        "каждого отдельную тему в подключённом форуме и сохраняет связь с ней. "
        "Каналы публикаций, аналитики, обсуждений и логов не обязательны и "
        "настраиваются позже только при необходимости."
    )



def _intro_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📘 1 · Короткий гид",
                    callback_data=_callback("guide", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🧩 2 · Выбрать модули",
                    callback_data=_callback("modules", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📁 3 · Основной архивный чат",
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
                    text="✖ Закрыть",
                    callback_data=_callback("close", workspace_id),
                )
            ],
        ]
    )



def _guide_text(workspace: Workspace) -> str:
    return (
        f"<b>📘 Как работает {escape(workspace.name)}</b>\n\n"
        "<b>Основной архив</b> — один форумный чат, в котором находятся ветки "
        "персонажей. Его достаточно подключить один раз.\n"
        "<b>Персонаж</b> — имя и карточка. После создания бот сам открывает в "
        "основном форуме тему с именем персонажа и сохраняет её связь.\n"
        "<b>Сохранение</b> — выберите персонажа кнопкой и отправьте фото, видео или файл; "
        "запись останется в изолированном архиве пространства и будет скопирована в тему.\n"
        "<b>Структура</b> — категории, вселенные и истории создаются пошагово кнопками.\n\n"
        "Не нужно заранее создавать темы вручную: ручная ссылка нужна только для "
        "исправления или переноса уже существующей темы.\n\n"
        "Дополнительные каналы нужны только отдельным функциям: канал публикаций "
        "для очереди, обсуждение для статистики и каналы public/analytics для "
        "channel posts. Они не блокируют запуск архива.\n\n"
        "Основной чат подключается командой "
        f"<code>/workspace_bind characters {workspace.id}</code> внутри самого чата."
    )



def _guide_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Понятно · выбрать модули",
                    callback_data=_callback("guidedone", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ В начало мастера",
                    callback_data=_callback("intro", workspace_id),
                )
            ],
        ]
    )



def _modules_text(workspace: Workspace) -> str:
    return (
        f"<b>🧩 Модули · {escape(workspace.name)}</b>\n\n"
        "Нажмите на разрешённый модуль, чтобы включить или выключить его.\n"
        "✅ включён · ➖ выключен · ⛔ недоступен по разрешению Стэл.\n\n"
        "Для первого запуска мастер потребует только один основной архивный чат, "
        "если включены персонажи или архив. Остальные подключения остаются "
        "необязательными."
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
    main = configured.get("characters")
    status = (
        "✅ " + escape(_destination_location(main))
        if main is not None
        else "❌ не подключён"
    )
    return (
        f"<b>📁 Основной архивный чат · {escape(workspace.name)}</b>\n\n"
        f"Статус: {status}\n\n"
        "Нужен один форумный чат, где размещаются ветки персонажей. В основном "
        "разделе этого чата отправьте:\n"
        f"<code>/workspace_bind characters {workspace.id}</code>\n\n"
        "После этого кнопка создания персонажа сама создаёт и закрепляет отдельную "
        "ветку с его именем. Отдельные чаты материалов, референсов, аналитики и "
        "логов для завершения установки не требуются."
    )



def _destinations_keyboard(
    workspace_id: int,
    destinations: tuple[WorkspaceDestination, ...],
) -> InlineKeyboardMarkup:
    configured = {item.destination_key for item in destinations}
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=("✅" if "characters" in configured else "▫️")
                    + " 📁 Как подключить основной чат",
                    callback_data=_callback("destinationhelp", workspace_id, "characters"),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 Проверить подключение",
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



def _destination_help_text(workspace: Workspace, key: WorkspaceDestinationKey) -> str:
    if key == "characters":
        return (
            f"<b>📁 Основной архив · {escape(workspace.name)}</b>\n\n"
            "1. Откройте один форумный чат архива.\n"
            "2. Добавьте бота администратором с правом управления темами.\n"
            "3. В основном разделе чата отправьте:\n"
            f"<code>/workspace_bind characters {workspace.id}</code>\n\n"
            "После этого создавайте персонажей кнопкой: бот сам создаёт и связывает "
            "их темы. Никакие другие чаты для обычного архива не обязательны."
        )
    spec = DESTINATION_SPECS[key]
    return (
        f"<b>{spec.emoji} {escape(spec.label)} · необязательное подключение</b>\n\n"
        f"{escape(spec.description)}\n\n"
        f"Команда внутри нужного чата: <code>{escape(spec.command_hint)}</code>"
    )



def _summary_keyboard(workspace_id: int, *, ready: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if ready:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚀 Завершить установку",
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
                    text="📁 Основной архивный чат",
                    callback_data=_callback("destinations", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="📘 Короткий гид",
                    callback_data=_callback("guide", workspace_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ В начало мастера",
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
        caller_member = await bot.get_chat_member(message.chat.id, user_id)
    except TelegramAPIError as error:
        await message.answer(
            "Не удалось проверить права бота или ваши права в чате: "
            + escape(str(error))
        )
        return
    caller_status = _status_value(caller_member)
    if caller_status not in {"administrator", "creator"}:
        await message.answer(
            "Подключить чат может только его администратор или владелец. "
            "Попросите администратора выполнить эту команду."
        )
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
        destination = await repository.configure_destination(
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
            channel_kind=spec.channel_kind,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
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
    spec = DESTINATION_SPECS[key]
    changed = await WorkspaceOnboardingRepository(database).unbind_destination(
        workspace_id=workspace.id,
        destination_key=key,
        channel_kind=spec.channel_kind,
    )
    await message.answer(
        "Назначение и связанная рабочая привязка удалены."
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
                "Модули подтверждены, основной архивный чат подключён, права бота "
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
