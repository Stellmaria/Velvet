from __future__ import annotations

from html import escape
from typing import cast
from uuid import uuid4

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.app.save_sessions import SaveUploadSessions
from velvet_bot.database import Database
from velvet_bot.domains.workspaces.character_management import (
    add_workspace_character_alias,
    create_workspace_character,
    delete_workspace_character,
    list_workspace_characters,
    load_workspace_character,
    rename_workspace_character,
    set_workspace_character_prompt_url,
    set_workspace_character_topic,
)
from velvet_bot.domains.workspaces.character_topics import ensure_character_archive_topic
from velvet_bot.domains.workspaces.models import Workspace, WorkspaceRole
from velvet_bot.domains.workspaces.onboarding import (
    DESTINATION_SPECS,
    WORKSPACE_DESTINATION_KEYS,
    WorkspaceDestinationKey,
    WorkspaceOnboardingRepository,
)
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID
from velvet_bot.domains.workspaces.product_service import (
    WorkspaceModuleAccessError,
    WorkspaceProductService,
)
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.presentation.telegram.routers.workspace_character_pickers import (
    WorkspaceCharacterPickerCallback,
    _render_card,
    _render_list,
)
from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    GuidedWorkspaceCallback,
    build_prompt_back_keyboard,
    guided_workspace_callback,
)
from velvet_bot.presentation.telegram.routers.workspace_onboarding import (
    _intro_keyboard,
    _intro_text,
)
from velvet_bot.services.telegram_topics import validate_topic_access
from velvet_bot.topics import parse_private_topic_link
from velvet_bot.workspace_ui import (
    WorkspaceCallback,
    build_taxonomy_keyboard,
    format_taxonomy,
    workspace_callback,
)

router = Router(name=__name__)
_PAGE_SIZE = 8
# Show only integrations with an active runtime consumer. Historical metadata
# destinations remain readable through status/commands for compatibility, but
# are not presented as if they routed data automatically.
_OPTIONAL_DESTINATION_KEYS: tuple[WorkspaceDestinationKey, ...] = (
    "public",
    "adult",
    "downloads",
    "watermarks",
    "publications",
    "discussion",
    "analytics",
)


class GuidedWorkspaceForm(StatesGroup):
    character_name = State()
    character_topic = State()
    character_rename = State()
    character_topic_edit = State()
    character_prompt = State()
    character_alias = State()
    category_label = State()
    category_emoji = State()
    universe_label = State()
    universe_emoji = State()
    story_short_label = State()
    story_title = State()


def _is_global_owner(user_id: int) -> bool:
    return int(user_id) == GLOBAL_WORKSPACE_CREATOR_ID


async def _edit(
    callback: CallbackQuery,
    *,
    text: str,
    reply_markup: InlineKeyboardMarkup,
    answer: str | None = None,
    show_alert: bool = False,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
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
    await callback.answer(answer, show_alert=show_alert)


async def _resolve_workspace(
    *,
    workspace_id: int,
    user_id: int,
    workspace_service: WorkspaceService,
    minimum_role: str = "editor",
) -> Workspace:
    workspace = await workspace_service.set_active_workspace(
        workspace_id=int(workspace_id),
        user_id=int(user_id),
        global_owner=_is_global_owner(user_id),
    )
    if workspace.is_system:
        raise WorkspaceAccessError(
            "Системный Velvet использует отдельное меню управления."
        )
    await workspace_service.require_role(
        workspace_id=workspace.id,
        user_id=int(user_id),
        minimum_role=cast(WorkspaceRole, minimum_role),
        global_owner=_is_global_owner(user_id),
    )
    return workspace


async def _enabled_modules(
    workspace_product_service: WorkspaceProductService,
    *,
    workspace_id: int,
    user_id: int,
) -> frozenset[str]:
    modules = await workspace_product_service.list_modules_for_member(
        workspace_id=int(workspace_id),
        actor_user_id=int(user_id),
        global_owner=_is_global_owner(user_id),
    )
    return frozenset(
        item.module_key
        for item in modules
        if item.is_allowed and item.is_enabled
    )


def _quick_keyboard(workspace_id: int, enabled: frozenset[str]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if "characters" in enabled:
        character_row = [
            InlineKeyboardButton(
                text="👥 Персонажи",
                callback_data=workspace_callback(
                    "module",
                    workspace_id=workspace_id,
                    module_key="characters",
                ),
            )
        ]
        if "archive" in enabled:
            character_row.append(
                InlineKeyboardButton(
                    text="💾 Сохранить",
                    callback_data=guided_workspace_callback(
                        "savepick",
                        workspace_id=workspace_id,
                    ),
                )
            )
        rows.append(character_row)
    if "taxonomy" in enabled:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🗂 Структура архива",
                    callback_data=workspace_callback(
                        "taxonomy",
                        workspace_id=workspace_id,
                    ),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🧭 Настройка архива",
                    callback_data=guided_workspace_callback(
                        "setup",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔌 Дополнительные подключения",
                    callback_data=guided_workspace_callback(
                        "connections",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Моё пространство",
                    callback_data=workspace_callback(
                        "home",
                        workspace_id=workspace_id,
                    ),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_quick(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    user_id: int,
    workspace_product_service: WorkspaceProductService,
) -> None:
    enabled = await _enabled_modules(
        workspace_product_service,
        workspace_id=workspace.id,
        user_id=user_id,
    )
    await _edit(
        callback,
        text=(
            f"<b>🧭 {escape(workspace.name)} · быстрые действия</b>\n\n"
            "Основные операции собраны кнопками. Команды остаются запасным способом, "
            "но запоминать их для обычной работы больше не требуется.\n\n"
            "Для запуска нужен один основной форумный чат. После его подключения бот "
            "сам создаёт отдельную тему для каждого нового персонажа и сохраняет её "
            "привязку внутри этого пространства. Материалы остаются в архиве персонажа "
            "и копируются в его тему; данные других пространств не смешиваются."
        ),
        reply_markup=_quick_keyboard(workspace.id, enabled),
    )


def _connections_keyboard(
    workspace_id: int,
    configured: frozenset[str],
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=("✅" if "characters" in configured else "▫️")
                + " 📁 Основной архив",
                callback_data=guided_workspace_callback(
                    "mainchat",
                    workspace_id=workspace_id,
                ),
            )
        ]
    ]
    for index, key in enumerate(_OPTIONAL_DESTINATION_KEYS, start=1):
        spec = DESTINATION_SPECS[key]
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅" if key in configured else "▫️")
                    + f" {spec.emoji} {spec.label}"[:54],
                    callback_data=guided_workspace_callback(
                        "conhelp",
                        workspace_id=workspace_id,
                        item_id=index,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Быстрые действия",
                callback_data=guided_workspace_callback(
                    "quick",
                    workspace_id=workspace_id,
                ),
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_connections(
    callback: CallbackQuery,
    *,
    workspace: Workspace,
    database: Database,
) -> None:
    configured = {
        item.destination_key: item
        for item in await WorkspaceOnboardingRepository(database).list_destinations(
            workspace.id
        )
    }
    main = configured.get("characters")
    main_status = (
        f"✅ {escape(main.chat_title or str(main.chat_id))}"
        if main is not None
        else "❌ не подключён"
    )
    optional_lines: list[str] = []
    for key in _OPTIONAL_DESTINATION_KEYS:
        spec = DESTINATION_SPECS[key]
        marker = "✅" if key in configured else "▫️"
        optional_lines.append(f"{marker} {spec.emoji} {escape(spec.label)}")
    await _edit(
        callback,
        text=(
            f"<b>🔌 Подключения · {escape(workspace.name)}</b>\n\n"
            f"<b>Основной архив:</b> {main_status}\n\n"
            "Для обычного личного архива нужен только основной форумный чат. "
            "Подключения ниже имеют рабочее назначение: канал публикаций — для "
            "очереди, обсуждение — для статистики реакций, а public/analytics — "
            "для статистики channel posts. Они не нужны для обычного архива.\n\n"
            "Персонажи, категории, истории и ссылки на темы хранятся в изолированной "
            "базе этого пространства. Файлы сохраняются в архиве выбранного персонажа "
            "и при настроенном форуме копируются в его персональную тему.\n\n"
            "<b>Необязательные подключения</b>\n"
            + "\n".join(optional_lines)
        ),
        reply_markup=_connections_keyboard(workspace.id, frozenset(configured)),
    )


def _main_chat_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ К подключениям",
                    callback_data=guided_workspace_callback(
                        "connections",
                        workspace_id=workspace_id,
                    ),
                )
            ]
        ]
    )


async def _render_main_chat(callback: CallbackQuery, workspace: Workspace) -> None:
    await _edit(
        callback,
        text=(
            f"<b>📁 Основной архив · {escape(workspace.name)}</b>\n\n"
            "1. Создайте или откройте один форумный чат архива.\n"
            "2. Добавьте бота администратором с правом управления темами.\n"
            "3. В основном разделе этого чата отправьте:\n"
            f"<code>/workspace_bind characters {workspace.id}</code>\n\n"
            "Этого достаточно для установки. Для каждого нового персонажа бот сам "
            "создаст отдельную тему с его именем и сохранит связь. Не создавайте "
            "такие темы вручную: ссылку можно изменить позднее из карточки персонажа. "
            "Остальные чаты не обязательны."
        ),
        reply_markup=_main_chat_keyboard(workspace.id),
    )


async def _character_page(
    database: Database,
    *,
    workspace_id: int,
    page: int,
):
    items = await list_workspace_characters(
        database,
        workspace_id=workspace_id,
        limit=500,
    )
    total_pages = max(1, (len(items) + _PAGE_SIZE - 1) // _PAGE_SIZE)
    normalized = min(max(0, int(page)), total_pages - 1)
    start = normalized * _PAGE_SIZE
    return items[start : start + _PAGE_SIZE], normalized, total_pages, len(items)


async def _save_picker_keyboard(
    database: Database,
    *,
    workspace_id: int,
    page: int,
) -> InlineKeyboardMarkup:
    items, normalized, total_pages, _ = await _character_page(
        database,
        workspace_id=workspace_id,
        page=page,
    )
    rows = [
        [
            InlineKeyboardButton(
                text=f"👤 {item.name}"[:60],
                callback_data=guided_workspace_callback(
                    "save",
                    workspace_id=workspace_id,
                    character_id=item.id,
                    page=normalized,
                ),
            )
        ]
        for item in items
    ]
    if total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=guided_workspace_callback(
                        "savepick",
                        workspace_id=workspace_id,
                        page=(normalized - 1) % total_pages,
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{normalized + 1} / {total_pages}",
                    callback_data=guided_workspace_callback(
                        "noop",
                        workspace_id=workspace_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=guided_workspace_callback(
                        "savepick",
                        workspace_id=workspace_id,
                        page=(normalized + 1) % total_pages,
                    ),
                ),
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="➕ Создать персонажа",
                    callback_data=guided_workspace_callback(
                        "cnew",
                        workspace_id=workspace_id,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Быстрые действия",
                    callback_data=guided_workspace_callback(
                        "quick",
                        workspace_id=workspace_id,
                    ),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_save_picker(
    callback: CallbackQuery,
    *,
    database: Database,
    workspace: Workspace,
    page: int,
) -> None:
    _, normalized, total_pages, total = await _character_page(
        database,
        workspace_id=workspace.id,
        page=page,
    )
    await _edit(
        callback,
        text=(
            f"<b>💾 Сохранить материал · {escape(workspace.name)}</b>\n\n"
            f"Персонажей: <b>{total}</b> · страница {normalized + 1}/{total_pages}\n\n"
            "Выберите персонажа, затем отправьте или перешлите фото, видео, "
            "анимацию либо файл."
        ),
        reply_markup=await _save_picker_keyboard(
            database,
            workspace_id=workspace.id,
            page=normalized,
        ),
    )


def _character_card_callback(workspace_id: int, character_id: int, page: int = 0) -> str:
    return WorkspaceCharacterPickerCallback(
        action="card",
        workspace_id=int(workspace_id),
        character_id=int(character_id),
        page=max(0, int(page)),
    ).pack()


def _active_save_keyboard(
    *,
    workspace_id: int,
    character_id: int,
    page: int = 0,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="✅ Закончить загрузку",
                    callback_data=guided_workspace_callback(
                        "savefinish",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=page,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Открыть карточку",
                    callback_data=guided_workspace_callback(
                        "saveopen",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=page,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="👤 Другой персонаж",
                    callback_data=guided_workspace_callback(
                        "savepick",
                        workspace_id=workspace_id,
                        page=page,
                    ),
                )
            ],
            [
                InlineKeyboardButton(
                    text="✖ Отменить режим",
                    callback_data=guided_workspace_callback(
                        "saveabort",
                        workspace_id=workspace_id,
                        character_id=character_id,
                        page=page,
                    ),
                )
            ],
        ]
    )


def _character_list_callback(workspace_id: int, page: int = 0) -> str:
    return WorkspaceCharacterPickerCallback(
        action="list",
        workspace_id=int(workspace_id),
        page=max(0, int(page)),
    ).pack()


def _after_character_keyboard(
    workspace_id: int,
    character_id: int,
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="👤 Открыть карточку",
                    callback_data=_character_card_callback(workspace_id, character_id),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К списку персонажей",
                    callback_data=_character_list_callback(workspace_id),
                )
            ],
        ]
    )


async def _finalize_character_creation(
    message: Message,
    state: FSMContext,
    database: Database,
    bot: Bot,
    *,
    topic_value: str | None,
) -> None:
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    name = str(data.get("character_name") or "").strip()
    if workspace_id <= 0 or not name:
        await state.clear()
        await message.answer("Сессия создания устарела. Откройте список персонажей заново.")
        return
    topic = None
    if topic_value:
        try:
            topic = parse_private_topic_link(topic_value)
            await validate_topic_access(bot, topic)
        except (ValueError, TelegramAPIError) as error:
            await message.answer(
                "Не удалось проверить ссылку на ветку. Проверьте ссылку и права бота.\n"
                f"<code>{escape(str(error))}</code>",
                reply_markup=build_prompt_back_keyboard(
                    workspace_id=workspace_id,
                    action="backlist",
                ),
            )
            return
    provision = None
    try:
        character, created = await create_workspace_character(
            database,
            workspace_id=workspace_id,
            name=name,
            created_by=message.from_user.id if message.from_user else None,
            created_in_chat=message.chat.id,
        )
        if topic is not None:
            await set_workspace_character_topic(
                database,
                workspace_id=workspace_id,
                character_id=character.id,
                topic=topic,
            )
        else:
            provision = await ensure_character_archive_topic(
                bot=bot,
                database=database,
                workspace_id=workspace_id,
                character=character,
            )
            topic = provision.topic
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await state.clear()
    topic_text = (
        f'<a href="{escape(topic.url, quote=True)}">Открыть тему персонажа</a>'
        if topic is not None
        else (
            "<b>⚠️ Тема пока не создана</b>\n"
            + escape(provision.error)
            if provision is not None and provision.error
            else "Тему можно назначить из карточки персонажа."
        )
    )
    creation_note = (
        "Тема создана автоматически и привязана к персонажу."
        if provision is not None and provision.created
        else "Тема уже была привязана к персонажу."
        if provision is not None and topic is not None
        else ""
    )
    await message.answer(
        (
            "<b>Персонаж создан</b>" if created else "<b>Персонаж уже существовал</b>"
        )
        + f"\n\nИмя: <b>{escape(character.name)}</b>\n"
        + (f"{creation_note}\n" if creation_note else "")
        + topic_text,
        reply_markup=_after_character_keyboard(workspace_id, character.id),
        disable_web_page_preview=True,
    )


async def _render_taxonomy_menu(
    target: CallbackQuery | Message,
    *,
    workspace: Workspace,
    workspace_product_service: WorkspaceProductService,
) -> None:
    categories = await workspace_product_service.list_categories(workspace.id)
    universes = await workspace_product_service.list_universes(workspace.id)
    stories = await workspace_product_service.list_stories(workspace_id=workspace.id)
    text = format_taxonomy(
        workspace,
        categories=categories,
        universes=universes,
        stories=stories,
    )
    keyboard = build_taxonomy_keyboard(workspace.id)
    if isinstance(target, CallbackQuery):
        await _edit(target, text=text, reply_markup=keyboard)
    else:
        await target.answer(text, reply_markup=keyboard)


def _taxonomy_prompt_keyboard(workspace_id: int) -> InlineKeyboardMarkup:
    return build_prompt_back_keyboard(
        workspace_id=workspace_id,
        action="backtax",
        text="↩️ К структуре архива",
    )


async def _start_category(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace: Workspace,
) -> None:
    await state.set_state(GuidedWorkspaceForm.category_label)
    await state.update_data(workspace_id=workspace.id)
    await _edit(
        callback,
        text=(
            "<b>➕ Новая категория</b>\n\n"
            "Отправьте понятное название категории. Технический ключ бот создаст сам."
        ),
        reply_markup=_taxonomy_prompt_keyboard(workspace.id),
    )


async def _start_universe(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace: Workspace,
) -> None:
    await state.set_state(GuidedWorkspaceForm.universe_label)
    await state.update_data(workspace_id=workspace.id)
    await _edit(
        callback,
        text=(
            "<b>➕ Новая вселенная</b>\n\n"
            "Отправьте название вселенной. Технический ключ бот создаст сам."
        ),
        reply_markup=_taxonomy_prompt_keyboard(workspace.id),
    )


async def _start_story(
    callback: CallbackQuery,
    *,
    state: FSMContext,
    workspace: Workspace,
    workspace_product_service: WorkspaceProductService,
) -> None:
    universes = await workspace_product_service.list_universes(workspace.id)
    if not universes:
        await callback.answer("Сначала создайте хотя бы одну вселенную.", show_alert=True)
        return
    rows = [
        [
            InlineKeyboardButton(
                text=f"{item.emoji} {item.label}"[:60],
                callback_data=guided_workspace_callback(
                    "storyuni",
                    workspace_id=workspace.id,
                    item_id=item.id,
                ),
            )
        ]
        for item in universes
    ]
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ К структуре архива",
                callback_data=guided_workspace_callback(
                    "backtax",
                    workspace_id=workspace.id,
                ),
            )
        ]
    )
    await state.update_data(workspace_id=workspace.id)
    await _edit(
        callback,
        text="<b>➕ Новая история</b>\n\nВыберите вселенную истории.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
    )


@router.callback_query(WorkspaceCallback.filter(F.action == "quick"))
async def handle_workspace_quick_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        await state.clear()
        workspace = await _resolve_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
        )
        await _render_quick(
            callback,
            workspace=workspace,
            user_id=callback.from_user.id,
            workspace_product_service=workspace_product_service,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)


@router.message(Command("cancel"))
async def handle_workspace_cancel(
    message: Message,
    state: FSMContext,
    save_upload_sessions: SaveUploadSessions,
) -> None:
    """Provide a visible escape hatch for every workspace interaction."""
    await state.clear()
    if message.from_user is not None:
        save_upload_sessions.stop(
            chat_id=message.chat.id,
            user_id=message.from_user.id,
        )
    await message.answer(
        "Текущее действие отменено. Откройте /start, затем «Моё пространство», "
        "чтобы продолжить с нужного раздела."
    )


@router.callback_query(
    WorkspaceCallback.filter(F.action.in_({"addcategory", "adduniverse", "addstory"}))
)
async def handle_guided_taxonomy_entry(
    callback: CallbackQuery,
    callback_data: WorkspaceCallback,
    state: FSMContext,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    try:
        workspace = await _resolve_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
        )
        if callback_data.action == "addcategory":
            await _start_category(callback, state=state, workspace=workspace)
        elif callback_data.action == "adduniverse":
            await _start_universe(callback, state=state, workspace=workspace)
        else:
            await _start_story(
                callback,
                state=state,
                workspace=workspace,
                workspace_product_service=workspace_product_service,
            )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)


@router.callback_query(GuidedWorkspaceCallback.filter())
async def handle_guided_workspace_callback(
    callback: CallbackQuery,
    callback_data: GuidedWorkspaceCallback,
    state: FSMContext,
    database: Database,
    bot: Bot,
    save_upload_sessions: SaveUploadSessions,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    action = callback_data.action
    if action == "noop":
        await callback.answer()
        return
    try:
        minimum_role = "owner" if action == "deleteconfirm" else "editor"
        workspace = await _resolve_workspace(
            workspace_id=callback_data.workspace_id,
            user_id=callback.from_user.id,
            workspace_service=workspace_service,
            minimum_role=minimum_role,
        )
        if action == "quick":
            await state.clear()
            await _render_quick(
                callback,
                workspace=workspace,
                user_id=callback.from_user.id,
                workspace_product_service=workspace_product_service,
            )
            return
        if action == "setup":
            await state.clear()
            repository = WorkspaceOnboardingRepository(database)
            current = await repository.ensure_started(
                workspace_id=workspace.id,
                user_id=callback.from_user.id,
            )
            await _edit(
                callback,
                text=_intro_text(workspace, resumed=current.started_at is not None),
                reply_markup=_intro_keyboard(workspace.id),
            )
            return
        if action == "connections":
            await state.clear()
            await _render_connections(callback, workspace=workspace, database=database)
            return
        if action == "mainchat":
            await state.clear()
            await _render_main_chat(callback, workspace)
            return
        if action == "conhelp":
            index = int(callback_data.item_id) - 1
            if index < 0 or index >= len(_OPTIONAL_DESTINATION_KEYS):
                raise ValueError("Подключение больше недоступно.")
            key = _OPTIONAL_DESTINATION_KEYS[index]
            spec = DESTINATION_SPECS[key]
            await _edit(
                callback,
                text=(
                    f"<b>{spec.emoji} {escape(spec.label)} · необязательно</b>\n\n"
                    f"{escape(spec.description)}\n\n"
                    "Подключайте этот чат только когда используете соответствующий "
                    "модуль. Команда отправляется внутри выбранного чата:\n"
                    f"<code>{escape(spec.command_hint)}</code>"
                ),
                reply_markup=build_prompt_back_keyboard(
                    workspace_id=workspace.id,
                    action="connections",
                    text="↩️ К подключениям",
                ),
            )
            return
        if action == "savepick":
            await state.clear()
            if isinstance(callback.message, Message):
                save_upload_sessions.stop(
                    chat_id=callback.message.chat.id,
                    user_id=callback.from_user.id,
                )
            await _render_save_picker(
                callback,
                database=database,
                workspace=workspace,
                page=callback_data.page,
            )
            return
        if action == "save":
            character = await load_workspace_character(
                database,
                workspace_id=workspace.id,
                character_id=callback_data.character_id,
            )
            if character is None:
                raise ValueError("Персонаж не найден в этом архиве.")
            if not isinstance(callback.message, Message):
                await callback.answer("Меню больше недоступно.", show_alert=True)
                return
            save_upload_sessions.start(
                chat_id=callback.message.chat.id,
                user_id=callback.from_user.id,
                character_name=character.name,
                character_id=character.id,
                workspace_id=workspace.id,
                command_message_id=callback.message.message_id,
            )
            await _edit(
                callback,
                text=(
                    f"<b>💾 Пакетная загрузка для {escape(character.name)}</b>\n\n"
                    "Отправьте или перешлите несколько фото, видео, анимаций либо "
                    "документов. Можно отправить Telegram-альбом: каждое сообщение "
                    "сохранится в текущем пространстве.\n\n"
                    "После последнего файла нажмите «Закончить загрузку». "
                    "Открытие карточки не останавливает режим, а отмена не удаляет "
                    "уже сохранённые материалы. Ожидание действует 10 минут после "
                    "последнего файла."
                ),
                reply_markup=_active_save_keyboard(
                    workspace_id=workspace.id,
                    character_id=character.id,
                    page=callback_data.page,
                ),
            )
            return
        if action == "saveopen":
            await _render_card(
                callback,
                database=database,
                workspace_id=workspace.id,
                character_id=callback_data.character_id,
                list_page=callback_data.page,
                answer="Режим загрузки остаётся активным.",
            )
            return
        if action in {"savefinish", "savecancel", "saveabort"}:
            stopped = None
            if isinstance(callback.message, Message):
                stopped = save_upload_sessions.stop(
                    chat_id=callback.message.chat.id,
                    user_id=callback.from_user.id,
                )
            if action == "saveabort":
                text = (
                    "Режим загрузки отменён. Уже сохранённые материалы не удалены. "
                    f"Обработано файлов: <b>{stopped.saved_count}</b>."
                    if stopped is not None
                    else "Активного режима загрузки уже нет."
                )
            else:
                text = (
                    f"Загрузка завершена. Обработано файлов: <b>{stopped.saved_count}</b>."
                    if stopped is not None
                    else "Активного режима загрузки уже нет."
                )
            await _edit(
                callback,
                text=text,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="↩️ К карточке",
                                callback_data=_character_card_callback(
                                    workspace.id,
                                    callback_data.character_id,
                                    callback_data.page,
                                ),
                            )
                        ]
                    ]
                ),
            )
            return
        if action == "cnew":
            await state.set_state(GuidedWorkspaceForm.character_name)
            await state.update_data(workspace_id=workspace.id)
            await _edit(
                callback,
                text=(
                    "<b>➕ Новый персонаж</b>\n\n"
                    "Отправьте имя персонажа одним сообщением."
                ),
                reply_markup=build_prompt_back_keyboard(
                    workspace_id=workspace.id,
                    action="backlist",
                    text="↩️ К списку персонажей",
                ),
            )
            return
        if action == "characterskiptopic":
            if not isinstance(callback.message, Message):
                await callback.answer("Меню больше недоступно.", show_alert=True)
                return
            await _finalize_character_creation(
                callback.message,
                state,
                database,
                bot,
                topic_value=None,
            )
            await callback.answer()
            return
        if action in {"rename", "topicedit", "prompt", "alias"}:
            state_map = {
                "rename": GuidedWorkspaceForm.character_rename,
                "topicedit": GuidedWorkspaceForm.character_topic_edit,
                "prompt": GuidedWorkspaceForm.character_prompt,
                "alias": GuidedWorkspaceForm.character_alias,
            }
            prompts = {
                "rename": "Отправьте новое имя персонажа.",
                "topicedit": "Отправьте ссылку на ветку персонажа.",
                "prompt": (
                    "Отправьте ссылку на пост с основным промтом персонажа. "
                    "Она появится в карточке и будет использоваться как справочная "
                    "ссылка в AI-проверках; изображения эта кнопка не загружает."
                ),
                "alias": "Отправьте новый алиас персонажа.",
            }
            await state.set_state(state_map[action])
            await state.update_data(
                workspace_id=workspace.id,
                character_id=callback_data.character_id,
                list_page=callback_data.page,
            )
            await _edit(
                callback,
                text=f"<b>{escape(prompts[action])}</b>",
                reply_markup=build_prompt_back_keyboard(
                    workspace_id=workspace.id,
                    character_id=callback_data.character_id,
                    action="backcard",
                    text="↩️ К карточке",
                ),
            )
            return
        if action in {"topicremove", "promptremove"}:
            if action == "topicremove":
                await set_workspace_character_topic(
                    database,
                    workspace_id=workspace.id,
                    character_id=callback_data.character_id,
                    topic=None,
                )
                notice = "Ссылка на ветку удалена."
            else:
                await set_workspace_character_prompt_url(
                    database,
                    workspace_id=workspace.id,
                    character_id=callback_data.character_id,
                    prompt_post_url=None,
                )
                notice = "Ссылка на промт удалена."
            await _edit(
                callback,
                text=notice,
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="↩️ К карточке",
                                callback_data=_character_card_callback(
                                    workspace.id,
                                    callback_data.character_id,
                                    callback_data.page,
                                ),
                            )
                        ]
                    ]
                ),
            )
            return
        if action == "deleteask":
            character = await load_workspace_character(
                database,
                workspace_id=workspace.id,
                character_id=callback_data.character_id,
            )
            if character is None:
                raise ValueError("Персонаж не найден в этом архиве.")
            await _edit(
                callback,
                text=(
                    "<b>Удалить персонажа?</b>\n\n"
                    f"{escape(character.name)} <code>#{character.id}</code>\n"
                    "Будут удалены его связи с материалами, историями, алиасами и веткой."
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="🗑 Да, удалить",
                                callback_data=guided_workspace_callback(
                                    "deleteconfirm",
                                    workspace_id=workspace.id,
                                    character_id=character.id,
                                    page=callback_data.page,
                                ),
                            )
                        ],
                        [
                            InlineKeyboardButton(
                                text="↩️ К карточке",
                                callback_data=_character_card_callback(
                                    workspace.id,
                                    character.id,
                                    callback_data.page,
                                ),
                            )
                        ],
                    ]
                ),
            )
            return
        if action == "deleteconfirm":
            deleted = await delete_workspace_character(
                database,
                workspace_id=workspace.id,
                character_id=callback_data.character_id,
            )
            await _edit(
                callback,
                text=f"Персонаж <b>{escape(deleted.name)}</b> удалён.",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="↩️ К списку персонажей",
                                callback_data=_character_list_callback(workspace.id),
                            )
                        ]
                    ]
                ),
            )
            return
        if action == "backlist":
            await state.clear()
            await _render_list(
                callback,
                database=database,
                workspace_id=workspace.id,
                workspace_name=workspace.name,
                page_number=callback_data.page,
            )
            return
        if action == "backcard":
            await state.clear()
            await _render_card(
                callback,
                database=database,
                workspace_id=workspace.id,
                character_id=callback_data.character_id,
                list_page=callback_data.page,
            )
            return
        if action == "backtax":
            await state.clear()
            await _render_taxonomy_menu(
                callback,
                workspace=workspace,
                workspace_product_service=workspace_product_service,
            )
            return
        if action == "catdefault":
            data = await state.get_data()
            label = str(data.get("taxonomy_label") or "").strip()
            item = await workspace_product_service.create_category(
                workspace_id=workspace.id,
                actor_user_id=callback.from_user.id,
                key=f"category-{uuid4().hex[:10]}",
                label=label,
                emoji=None,
                global_owner=_is_global_owner(callback.from_user.id),
            )
            await state.clear()
            await _edit(
                callback,
                text=f"Категория сохранена: {item.emoji} <b>{escape(item.label)}</b>.",
                reply_markup=build_taxonomy_keyboard(workspace.id),
            )
            return
        if action == "unidefaultemoji":
            await state.update_data(taxonomy_emoji="🎭")
            await _edit(
                callback,
                text="<b>Истории обязательны для этой вселенной?</b>",
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="✅ Да",
                                callback_data=guided_workspace_callback(
                                    "unirequired",
                                    workspace_id=workspace.id,
                                    item_id=1,
                                ),
                            ),
                            InlineKeyboardButton(
                                text="➖ Нет",
                                callback_data=guided_workspace_callback(
                                    "unirequired",
                                    workspace_id=workspace.id,
                                    item_id=0,
                                ),
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                text="↩️ К структуре архива",
                                callback_data=guided_workspace_callback(
                                    "backtax",
                                    workspace_id=workspace.id,
                                ),
                            )
                        ],
                    ]
                ),
            )
            return
        if action == "unirequired":
            data = await state.get_data()
            item = await workspace_product_service.create_universe(
                workspace_id=workspace.id,
                actor_user_id=callback.from_user.id,
                key=f"universe-{uuid4().hex[:10]}",
                label=str(data.get("taxonomy_label") or ""),
                emoji=str(data.get("taxonomy_emoji") or "🎭"),
                requires_story=bool(callback_data.item_id),
                global_owner=_is_global_owner(callback.from_user.id),
            )
            await state.clear()
            await _edit(
                callback,
                text=f"Вселенная сохранена: {item.emoji} <b>{escape(item.label)}</b>.",
                reply_markup=build_taxonomy_keyboard(workspace.id),
            )
            return
        if action == "storyuni":
            universes = await workspace_product_service.list_universes(workspace.id)
            universe = next(
                (item for item in universes if item.id == callback_data.item_id),
                None,
            )
            if universe is None:
                raise ValueError("Вселенная больше недоступна.")
            await state.set_state(GuidedWorkspaceForm.story_short_label)
            await state.update_data(
                workspace_id=workspace.id,
                story_universe_key=universe.key,
            )
            await _edit(
                callback,
                text=(
                    f"<b>Новая история · {escape(universe.label)}</b>\n\n"
                    "Отправьте короткую подпись, например «СН» или «Сезон 1»."
                ),
                reply_markup=_taxonomy_prompt_keyboard(workspace.id),
            )
            return
        await callback.answer("Неизвестное действие меню.", show_alert=True)
    except (
        ValueError,
        WorkspaceAccessError,
        WorkspaceModuleAccessError,
    ) as error:
        await callback.answer(str(error), show_alert=True)


@router.message(GuidedWorkspaceForm.character_name)
async def handle_character_name(
    message: Message,
    state: FSMContext,
    database: Database,
    bot: Bot,
) -> None:
    name = " ".join((message.text or "").split())
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    if not name:
        await message.answer("Имя не может быть пустым.")
        return
    await state.update_data(character_name=name)
    await _finalize_character_creation(
        message,
        state,
        database,
        bot,
        topic_value=None,
    )


@router.message(GuidedWorkspaceForm.character_topic)
async def handle_character_topic(
    message: Message,
    state: FSMContext,
    database: Database,
    bot: Bot,
) -> None:
    await _finalize_character_creation(
        message,
        state,
        database,
        bot,
        topic_value=(message.text or "").strip(),
    )


async def _character_state_data(state: FSMContext) -> tuple[int, int, int]:
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    character_id = int(data.get("character_id") or 0)
    list_page = int(data.get("list_page") or 0)
    if workspace_id <= 0 or character_id <= 0:
        raise ValueError("Сессия персонажа устарела. Откройте карточку заново.")
    return workspace_id, character_id, list_page


@router.message(GuidedWorkspaceForm.character_rename)
async def handle_character_rename(
    message: Message,
    state: FSMContext,
    database: Database,
) -> None:
    try:
        workspace_id, character_id, page = await _character_state_data(state)
        item = await rename_workspace_character(
            database,
            workspace_id=workspace_id,
            character_id=character_id,
            new_name=message.text or "",
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await state.clear()
    await message.answer(
        f"Имя изменено: <b>{escape(item.name)}</b>.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="↩️ К карточке",
                        callback_data=_character_card_callback(
                            workspace_id,
                            character_id,
                            page,
                        ),
                    )
                ]
            ]
        ),
    )


@router.message(GuidedWorkspaceForm.character_topic_edit)
async def handle_character_topic_edit(
    message: Message,
    state: FSMContext,
    database: Database,
    bot: Bot,
) -> None:
    try:
        workspace_id, character_id, page = await _character_state_data(state)
        topic = parse_private_topic_link((message.text or "").strip())
        await validate_topic_access(bot, topic)
        await set_workspace_character_topic(
            database,
            workspace_id=workspace_id,
            character_id=character_id,
            topic=topic,
        )
    except (ValueError, TelegramAPIError) as error:
        await message.answer(escape(str(error)))
        return
    await state.clear()
    await message.answer(
        "Ссылка на ветку обновлена.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="↩️ К карточке",
                        callback_data=_character_card_callback(
                            workspace_id,
                            character_id,
                            page,
                        ),
                    )
                ]
            ]
        ),
    )


@router.message(GuidedWorkspaceForm.character_prompt)
async def handle_character_prompt(
    message: Message,
    state: FSMContext,
    database: Database,
) -> None:
    try:
        workspace_id, character_id, page = await _character_state_data(state)
        await set_workspace_character_prompt_url(
            database,
            workspace_id=workspace_id,
            character_id=character_id,
            prompt_post_url=(message.text or "").strip(),
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await state.clear()
    await message.answer(
        "Ссылка на промт сохранена.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="↩️ К карточке",
                        callback_data=_character_card_callback(
                            workspace_id,
                            character_id,
                            page,
                        ),
                    )
                ]
            ]
        ),
    )


@router.message(GuidedWorkspaceForm.character_alias)
async def handle_character_alias(
    message: Message,
    state: FSMContext,
    database: Database,
) -> None:
    try:
        workspace_id, character_id, page = await _character_state_data(state)
        alias = await add_workspace_character_alias(
            database,
            workspace_id=workspace_id,
            character_id=character_id,
            alias=message.text or "",
            created_by=message.from_user.id if message.from_user else None,
        )
    except ValueError as error:
        await message.answer(escape(str(error)))
        return
    await state.clear()
    await message.answer(
        f"Алиас сохранён: <code>{escape(alias.alias)}</code>.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="↩️ К карточке",
                        callback_data=_character_card_callback(
                            workspace_id,
                            character_id,
                            page,
                        ),
                    )
                ]
            ]
        ),
    )


@router.message(GuidedWorkspaceForm.category_label)
async def handle_category_label(message: Message, state: FSMContext) -> None:
    label = " ".join((message.text or "").split())
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    if not label:
        await message.answer("Название не может быть пустым.")
        return
    await state.set_state(GuidedWorkspaceForm.category_emoji)
    await state.update_data(taxonomy_label=label)
    await message.answer(
        "Отправьте emoji категории или используйте стандартный значок.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📁 Стандартный",
                        callback_data=guided_workspace_callback(
                            "catdefault",
                            workspace_id=workspace_id,
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="↩️ К структуре архива",
                        callback_data=guided_workspace_callback(
                            "backtax",
                            workspace_id=workspace_id,
                        ),
                    )
                ],
            ]
        ),
    )


@router.message(GuidedWorkspaceForm.category_emoji)
async def handle_category_emoji(
    message: Message,
    state: FSMContext,
    workspace_product_service: WorkspaceProductService,
) -> None:
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    try:
        item = await workspace_product_service.create_category(
            workspace_id=workspace_id,
            actor_user_id=message.from_user.id if message.from_user else 0,
            key=f"category-{uuid4().hex[:10]}",
            label=str(data.get("taxonomy_label") or ""),
            emoji=(message.text or "").strip(),
            global_owner=_is_global_owner(message.from_user.id if message.from_user else 0),
        )
    except (ValueError, WorkspaceAccessError, WorkspaceModuleAccessError) as error:
        await message.answer(escape(str(error)))
        return
    await state.clear()
    await message.answer(
        f"Категория сохранена: {item.emoji} <b>{escape(item.label)}</b>.",
        reply_markup=build_taxonomy_keyboard(workspace_id),
    )


@router.message(GuidedWorkspaceForm.universe_label)
async def handle_universe_label(message: Message, state: FSMContext) -> None:
    label = " ".join((message.text or "").split())
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    if not label:
        await message.answer("Название не может быть пустым.")
        return
    await state.set_state(GuidedWorkspaceForm.universe_emoji)
    await state.update_data(taxonomy_label=label)
    await message.answer(
        "Отправьте emoji вселенной или используйте стандартный значок.",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🎭 Стандартный",
                        callback_data=guided_workspace_callback(
                            "unidefaultemoji",
                            workspace_id=workspace_id,
                        ),
                    )
                ],
                [
                    InlineKeyboardButton(
                        text="↩️ К структуре архива",
                        callback_data=guided_workspace_callback(
                            "backtax",
                            workspace_id=workspace_id,
                        ),
                    )
                ],
            ]
        ),
    )


@router.message(GuidedWorkspaceForm.universe_emoji)
async def handle_universe_emoji(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    await state.update_data(taxonomy_emoji=(message.text or "").strip())
    await message.answer(
        "<b>Истории обязательны для этой вселенной?</b>",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Да",
                        callback_data=guided_workspace_callback(
                            "unirequired",
                            workspace_id=workspace_id,
                            item_id=1,
                        ),
                    ),
                    InlineKeyboardButton(
                        text="➖ Нет",
                        callback_data=guided_workspace_callback(
                            "unirequired",
                            workspace_id=workspace_id,
                            item_id=0,
                        ),
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="↩️ К структуре архива",
                        callback_data=guided_workspace_callback(
                            "backtax",
                            workspace_id=workspace_id,
                        ),
                    )
                ],
            ]
        ),
    )


@router.message(GuidedWorkspaceForm.story_short_label)
async def handle_story_short_label(message: Message, state: FSMContext) -> None:
    value = " ".join((message.text or "").split())
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    if not value:
        await message.answer("Короткая подпись не может быть пустой.")
        return
    await state.set_state(GuidedWorkspaceForm.story_title)
    await state.update_data(story_short_label=value)
    await message.answer(
        "Отправьте полное название истории.",
        reply_markup=_taxonomy_prompt_keyboard(workspace_id),
    )


@router.message(GuidedWorkspaceForm.story_title)
async def handle_story_title(
    message: Message,
    state: FSMContext,
    workspace_product_service: WorkspaceProductService,
) -> None:
    data = await state.get_data()
    workspace_id = int(data.get("workspace_id") or 0)
    try:
        item = await workspace_product_service.create_story(
            workspace_id=workspace_id,
            actor_user_id=message.from_user.id if message.from_user else 0,
            universe_key=str(data.get("story_universe_key") or ""),
            key=f"story-{uuid4().hex[:10]}",
            short_label=str(data.get("story_short_label") or ""),
            title=message.text or "",
            global_owner=_is_global_owner(message.from_user.id if message.from_user else 0),
        )
    except (ValueError, WorkspaceAccessError, WorkspaceModuleAccessError) as error:
        await message.answer(escape(str(error)))
        return
    await state.clear()
    await message.answer(
        f"История сохранена: <b>{escape(item.short_label)} · {escape(item.title)}</b>.",
        reply_markup=build_taxonomy_keyboard(workspace_id),
    )


__all__ = (
    "GuidedWorkspaceCallback",
    "GuidedWorkspaceForm",
    "router",
)
