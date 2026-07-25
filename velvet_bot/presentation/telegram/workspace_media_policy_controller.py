from __future__ import annotations

from dataclasses import dataclass
from html import escape

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.database import Database
from velvet_bot.domains.archive.models import ArchivePage
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.onboarding import WorkspaceOnboardingRepository
from velvet_bot.domains.workspaces.product_service import WorkspaceProductService
from velvet_bot.domains.workspaces.service import WorkspaceAccessError, WorkspaceService
from velvet_bot.domains.workspaces.watermark_assets import (
    WorkspaceWatermarkAssetRepository,
)
from velvet_bot.presentation.telegram.routers.workspace_guided_ui import (
    guided_workspace_callback,
)
from velvet_bot.presentation.telegram.workspace_archive_access import (
    is_global_workspace_owner,
    load_workspace_archive_action_page,
    resolve_workspace_archive_access,
)
from velvet_bot.presentation.telegram.workspace_personal_archive_contract import (
    WorkspacePersonalArchiveAction,
    WorkspacePersonalArchiveActionFilter,
    workspace_personal_archive_callback,
)
from velvet_bot.workspace_ui import workspace_callback

_DOWNLOAD_AUDIENCE_LABELS = {
    "disabled": "🚫 запрещено",
    "all": "🌐 всем читателям архива",
    "subscribers": "🔐 подписчикам выбранного канала",
}
_DOWNLOAD_VARIANT_LABELS = {
    "watermark": "🖼 одобренная watermark-копия",
    "original": "📦 сохранённый оригинал",
}
_DOWNLOAD_AUDIENCE_ACTIONS = {
    "dlaudnone": "disabled",
    "dlaudall": "all",
    "dlaudsub": "subscribers",
}
_DOWNLOAD_VARIANT_ACTIONS = {
    "dlvarwm": "watermark",
    "dlvarorig": "original",
}
_MEDIA_POLICY_ACTIONS = frozenset(
    {
        "noop",
        "settings",
        "mediahelp",
        *_DOWNLOAD_AUDIENCE_ACTIONS,
        *_DOWNLOAD_VARIANT_ACTIONS,
    }
)
_OWNER_POLICY_ACTIONS = _MEDIA_POLICY_ACTIONS - {"noop"}


@dataclass(frozen=True, slots=True)
class WorkspaceMediaPolicyPresentation:
    text: str
    keyboard: InlineKeyboardMarkup


def build_workspace_media_policy_keyboard(
    *,
    workspace_id: int,
    character_id: int,
    offset: int,
    media_id: int,
    download_audience: str,
    download_variant: str,
) -> InlineKeyboardMarkup:
    common = {
        "workspace_id": workspace_id,
        "character_id": character_id,
        "offset": offset,
        "media_id": media_id,
    }
    rows: list[list[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text="Кто может скачивать",
                callback_data=workspace_personal_archive_callback("noop", **common),
            )
        ]
    ]
    for action, audience, label in (
        ("dlaudnone", "disabled", "🚫 Никто"),
        ("dlaudall", "all", "🌐 Все читатели"),
        ("dlaudsub", "subscribers", "🔐 Подписчики канала"),
    ):
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if download_audience == audience else "") + label,
                    callback_data=workspace_personal_archive_callback(action, **common),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="Какую версию выдавать",
                callback_data=workspace_personal_archive_callback("noop", **common),
            )
        ]
    )
    for action, variant, label in (
        ("dlvarwm", "watermark", "🖼 Только с watermark"),
        ("dlvarorig", "original", "📦 Оригинал"),
    ):
        rows.append(
            [
                InlineKeyboardButton(
                    text=("✅ " if download_variant == variant else "") + label,
                    callback_data=workspace_personal_archive_callback(action, **common),
                )
            ]
        )
    rows.extend(
        [
            [
                InlineKeyboardButton(
                    text="🔌 Каналы доступа",
                    callback_data=guided_workspace_callback(
                        "connections",
                        workspace_id=workspace_id,
                    ),
                ),
                InlineKeyboardButton(
                    text="💧 Настроить watermark",
                    callback_data=workspace_callback(
                        "module",
                        workspace_id=workspace_id,
                        module_key="watermark",
                    ),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ К материалу",
                    callback_data=workspace_personal_archive_callback("show", **common),
                )
            ],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def build_workspace_media_policy_presentation(
    database: Database,
    *,
    workspace_product_service: WorkspaceProductService,
    workspace: Workspace,
    page: ArchivePage,
) -> WorkspaceMediaPolicyPresentation:
    if page.media is None:
        raise ValueError("Архив персонажа пока пуст.")
    settings = await workspace_product_service.get_settings(workspace.id)
    channels = await workspace_product_service.list_channels(workspace.id)
    channel_kinds = {item.kind for item in channels}
    destinations = await WorkspaceOnboardingRepository(database).list_destinations(
        workspace.id
    )
    destination_keys = {item.destination_key for item in destinations}
    watermark_asset = await WorkspaceWatermarkAssetRepository(database).get(workspace.id)
    original_storage = (
        "форум персонажей подключён"
        if "characters" in destination_keys
        else "форум персонажей не подключён"
    )
    watermark_storage = (
        "назначение подключено"
        if "watermarks" in destination_keys
        else "назначение не подключено"
    )
    watermark_template = "настроен" if watermark_asset is not None else "не настроен"
    text = (
        f"<b>⚙️ Доступ к медиа · {escape(workspace.name)}</b>\n\n"
        "Публичный архив: "
        f"<b>{'включён' if settings.public_archive_enabled else 'выключен'}</b>\n"
        "Кто может скачивать: "
        f"<b>{_DOWNLOAD_AUDIENCE_LABELS[settings.download_audience]}</b>\n"
        "Какую версию выдавать: "
        f"<b>{_DOWNLOAD_VARIANT_LABELS[settings.download_variant]}</b>\n"
        "Канал проверки скачивания: "
        f"<b>{'подключён' if 'download' in channel_kinds else 'не подключён'}</b>\n"
        f"Канал +18: <b>{'подключён' if 'adult' in channel_kinds else 'не подключён'}</b>\n"
        f"Оригиналы: <b>{original_storage}</b>\n"
        f"Watermark-копии: <b>{watermark_storage}</b>\n"
        f"Шаблон watermark: <b>{watermark_template}</b>\n\n"
        "По умолчанию карточки отправляются с защитой Telegram от пересылки и "
        "сохранения. Кнопка скачивания появляется у читателя только когда это "
        "разрешают оба параметра. Оригинал хранится в теме персонажа и не "
        "заменяется: подтверждённый watermark сохраняется отдельным Telegram-файлом "
        "в выбранном назначении.\n\n"
        "⚠️ Для изображений больше 20 МБ cloud Bot API может не построить превью. "
        "Владелец всё равно видит кнопку оригинала; читатель получает файл только "
        "когда политика скачивания это разрешает."
    )
    return WorkspaceMediaPolicyPresentation(
        text=text,
        keyboard=build_workspace_media_policy_keyboard(
            workspace_id=workspace.id,
            character_id=page.character.id,
            offset=page.offset,
            media_id=page.media.id,
            download_audience=settings.download_audience,
            download_variant=settings.download_variant,
        ),
    )


async def show_workspace_media_policy(
    callback: CallbackQuery,
    *,
    database: Database,
    workspace_product_service: WorkspaceProductService,
    workspace: Workspace,
    page: ArchivePage,
    alert: str | None = None,
) -> None:
    presentation = await build_workspace_media_policy_presentation(
        database,
        workspace_product_service=workspace_product_service,
        workspace=workspace,
        page=page,
    )
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    if callback.message.text:
        try:
            await callback.message.edit_text(
                presentation.text,
                reply_markup=presentation.keyboard,
            )
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                raise
    else:
        await callback.message.answer(
            presentation.text,
            reply_markup=presentation.keyboard,
        )
    await callback.answer(alert)


async def show_workspace_media_help(
    callback: CallbackQuery,
    *,
    workspace_id: int,
    page: ArchivePage,
) -> None:
    if page.media is None:
        await callback.answer("Архив персонажа пока пуст.", show_alert=True)
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    text = (
        "<b>Справка по карточке персонажа</b>\n\n"
        "<b>Промт</b> — ссылка на исходный промт персонажа. Она нужна как "
        "творческий референс и для AI-проверок; изображения эта кнопка не загружает.\n\n"
        "<b>Сохранить / Загрузить медиа</b> — выбирает персонажа и включает "
        "пакетную загрузку. Можно прислать несколько фото, альбом, видео и "
        "документы подряд, затем нажать «Завершить загрузку».\n\n"
        "<b>+ Создать персонажа</b> — создаёт карточку и архивную ветку; медиа "
        "добавляются после создания через «Загрузить медиа».\n\n"
        "<b>Лайк</b> и <b>Подписаться</b> доступны владельцу и читателям "
        "публичного архива. <b>Скачать оригинал</b> всегда доступно владельцу; "
        "для читателей кнопкой «Доступ и скачивание» отдельно выбираются "
        "аудитория и версия файла. По умолчанию скачивание запрещено.\n\n"
        "<b>Быстрый watermark</b> создаёт отдельную версию, не заменяя оригинал. "
        "<b>Доработка</b> кладёт материал в общую очередь и скрывает его из "
        "публичной выдачи. После проверки владелец возвращает работу кнопкой "
        "«Вернуть в публичный». <b>Скрыть</b>, <b>+18</b> и <b>Блюр</b> "
        "управляют видимостью конкретного материала."
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="↩️ К материалу",
                    callback_data=workspace_personal_archive_callback(
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


async def handle_workspace_media_policy(
    callback: CallbackQuery,
    archive_action: WorkspacePersonalArchiveAction,
    database: Database,
    workspace_service: WorkspaceService,
    workspace_product_service: WorkspaceProductService,
) -> None:
    action = archive_action.action
    try:
        workspace, owner_access = await resolve_workspace_archive_access(
            workspace_service=workspace_service,
            workspace_product_service=workspace_product_service,
            user_id=callback.from_user.id,
            workspace_id=archive_action.workspace_id,
        )
    except WorkspaceAccessError as error:
        await callback.answer(str(error), show_alert=True)
        return

    if action in _OWNER_POLICY_ACTIONS and not owner_access:
        await callback.answer(
            "Эта кнопка доступна только владельцу пространства.",
            show_alert=True,
        )
        return
    if action == "noop":
        await callback.answer()
        return

    page = await load_workspace_archive_action_page(
        callback,
        archive_action,
        database,
        workspace=workspace,
    )
    if page is None:
        return

    if action == "settings":
        await show_workspace_media_policy(
            callback,
            database=database,
            workspace_product_service=workspace_product_service,
            workspace=workspace,
            page=page,
        )
        return
    if action == "mediahelp":
        await show_workspace_media_help(
            callback,
            workspace_id=workspace.id,
            page=page,
        )
        return

    settings = await workspace_product_service.get_settings(workspace.id)
    audience = _DOWNLOAD_AUDIENCE_ACTIONS.get(
        action,
        settings.download_audience,
    )
    variant = _DOWNLOAD_VARIANT_ACTIONS.get(
        action,
        settings.download_variant,
    )
    channels = await workspace_product_service.list_channels(workspace.id)
    channel_kinds = {item.kind for item in channels}
    destinations = await WorkspaceOnboardingRepository(database).list_destinations(
        workspace.id
    )
    destination_keys = {item.destination_key for item in destinations}
    watermark_asset = await WorkspaceWatermarkAssetRepository(database).get(
        workspace.id
    )
    if audience == "subscribers" and "download" not in channel_kinds:
        await show_workspace_media_policy(
            callback,
            database=database,
            workspace_product_service=workspace_product_service,
            workspace=workspace,
            page=page,
            alert="Сначала подключите канал «Проверка скачивания».",
        )
        return
    if audience != "disabled" and variant == "watermark" and watermark_asset is None:
        await show_workspace_media_policy(
            callback,
            database=database,
            workspace_product_service=workspace_product_service,
            workspace=workspace,
            page=page,
            alert="Сначала загрузите шаблон watermark.",
        )
        return
    if (
        audience != "disabled"
        and variant == "watermark"
        and "watermarks" not in destination_keys
    ):
        await show_workspace_media_policy(
            callback,
            database=database,
            workspace_product_service=workspace_product_service,
            workspace=workspace,
            page=page,
            alert="Сначала подключите назначение «Watermark-копии».",
        )
        return

    await workspace_product_service.set_download_policy(
        workspace_id=workspace.id,
        actor_user_id=callback.from_user.id,
        download_audience=audience,
        download_variant=variant,
        global_owner=is_global_workspace_owner(callback.from_user.id),
    )
    await show_workspace_media_policy(
        callback,
        database=database,
        workspace_product_service=workspace_product_service,
        workspace=workspace,
        page=page,
        alert="Настройка скачивания сохранена.",
    )


def register_workspace_media_policy(router: Router) -> None:
    router.callback_query.register(
        handle_workspace_media_policy,
        WorkspacePersonalArchiveActionFilter(*sorted(_MEDIA_POLICY_ACTIONS)),
    )


__all__ = (
    "WorkspaceMediaPolicyPresentation",
    "build_workspace_media_policy_keyboard",
    "build_workspace_media_policy_presentation",
    "handle_workspace_media_policy",
    "register_workspace_media_policy",
    "show_workspace_media_help",
    "show_workspace_media_policy",
)
