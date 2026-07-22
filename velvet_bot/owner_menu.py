from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.presentation.telegram.analytics_navigation import AnalyticsCallback
from velvet_bot.presentation.telegram.routers.characters.contracts import (
    AdminDirectoryCallback,
)
from velvet_bot.presentation.telegram.routers.publication.center import (
    PublicationCallback,
)
from velvet_bot.presentation.telegram.routers.quality_operations_controllers.backup_center import (
    BackupCallback,
)
from velvet_bot.owner_callbacks import (
    OwnerMenuCallback,
    owner_action_callback,
    owner_callback,
)
from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_admin_ui import (
    workspace_admin_callback,
)
from velvet_bot.presentation.telegram.routers.supervisor.control import SupervisorCallback
from velvet_bot.presentation.telegram.routers.system import SystemCallback
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.quality_ui import quality_callback
from velvet_bot.watermark_ui import WatermarkCallback
from velvet_bot.workspace_ui import workspace_callback


def build_owner_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Архив",
                    callback_data=PublicArchiveCallback(action="categories").pack(),
                ),
                InlineKeyboardButton(
                    text="👥 Персонажи",
                    callback_data=AdminDirectoryCallback(action="categories").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🏛 Пространства",
                    callback_data=workspace_admin_callback("home"),
                ),
                InlineKeyboardButton(
                    text="🌐 Публичные архивы",
                    callback_data=workspace_callback("publics"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="💧 Знак",
                    callback_data=WatermarkCallback(action="start").pack(),
                ),
                InlineKeyboardButton(
                    text="🧰 Действия",
                    callback_data=owner_action_callback("menu"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🛡 Supervisor",
                    callback_data=SupervisorCallback(action="status").pack(),
                ),
                InlineKeyboardButton(
                    text="⚙️ Система",
                    callback_data=SystemCallback(action="overview").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🤖 Qwen",
                    callback_data=quality_callback("ai_menu"),
                ),
                InlineKeyboardButton(
                    text="💾 Backup",
                    callback_data=BackupCallback(action="menu").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📊 Аналитика",
                    callback_data=AnalyticsCallback(action="menu", period="all").pack(),
                ),
                InlineKeyboardButton(
                    text="📣 Публикации",
                    callback_data=PublicationCallback(action="menu").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="ℹ️ Справка",
                    callback_data=owner_callback("help"),
                ),
                InlineKeyboardButton(
                    text="✖ Закрыть",
                    callback_data=owner_callback("close"),
                ),
            ],
        ]
    )


def build_owner_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🏠 Главная",
                    callback_data=owner_callback("menu"),
                )
            ]
        ]
    )


def owner_menu_text(first_name: str = "") -> str:
    greeting = f", {first_name}" if first_name else ""
    return (
        f"<b>Velvet Archive · центр управления</b>{greeting}\n\n"
        "Все основные разделы и прежние slash-действия доступны кнопками. "
        "Опасные операции требуют подтверждения, а значения, ссылки и файлы "
        "передаются через подписанные формы ответа."
    )


def owner_help_text() -> str:
    return (
        "<b>Как устроено кнопочное управление</b>\n\n"
        "🖼 <b>Архив</b> — публичный просмотр материалов.\n"
        "👥 <b>Персонажи</b> — карточки, категории, вселенные, истории, промты "
        "и переходы к медиа.\n"
        "🏛 <b>Пространства</b> — отдельная панель Стэл: выдача права создать "
        "личный архив, список пользователей и пространств, а также разрешение "
        "или запрет каждого модуля кнопками.\n"
        "🌐 <b>Публичные архивы</b> — просмотр пространств, владельцы которых "
        "включили публичный read-only режим.\n"
        "💧 <b>Водяной знак</b> — отправка изображения в локальную Krita, "
        "preview, выбор угла, цвета, прозрачности, размера и отступа.\n"
        "🧰 <b>Все действия</b> — формы создания персонажей, тем, историй, "
        "референсов, алиасов, сохранения медиа и импорта.\n"
        "🛡 <b>Supervisor и Codex</b> — состояние процесса, логи, Git, "
        "перезапуск, откат и задачи Codex.\n"
        "⚙️ <b>Система</b> — база, воркеры, очереди, версия и отчёт.\n"
        "🤖 <b>Qwen</b> — архивная проверка, доработка, референсы, промт против результата, "
        "целостность сетов, калибровка Qwen и архивный аудит.\n"
        "💾 <b>Резервные копии</b> — создание, проверка, история и очистка.\n"
        "📊 <b>Аналитика</b> — канал, промты, персонажи, хэштеги и обсуждения.\n"
        "📣 <b>Публикации</b> — черновики, очередь, ошибки и опубликованные посты.\n\n"
        "Для действий с конкретным файлом бот сначала присылает форму. Ответьте "
        "на неё нужным фото, видео, постом или экспортом. Старые slash-обработчики "
        "сохранены только как аварийный резерв и в меню Telegram не показываются."
    )


__all__ = (
    "OwnerMenuCallback",
    "build_owner_back_keyboard",
    "build_owner_main_keyboard",
    "owner_callback",
    "owner_help_text",
    "owner_menu_text",
)
