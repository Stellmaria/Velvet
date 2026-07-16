from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.handlers.admin_directory import AdminDirectoryCallback
from velvet_bot.handlers.analytics_dashboard import AnalyticsCallback
from velvet_bot.handlers.backup_center import BackupCallback
from velvet_bot.handlers.publication_center import PublicationCallback
from velvet_bot.handlers.supervisor_control import SupervisorCallback
from velvet_bot.handlers.system_center import SystemCallback
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.quality_ui import quality_callback


class OwnerMenuCallback(CallbackData, prefix="own"):
    action: str


def owner_callback(action: str) -> str:
    return OwnerMenuCallback(action=action).pack()


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
                    text="🛡 Supervisor и Codex",
                    callback_data=SupervisorCallback(action="status").pack(),
                ),
                InlineKeyboardButton(
                    text="⚙️ Система",
                    callback_data=SystemCallback(action="overview").pack(),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🧬 Контроль качества",
                    callback_data=quality_callback("menu"),
                ),
                InlineKeyboardButton(
                    text="💾 Резервные копии",
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
                    text="ℹ️ Как пользоваться",
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
                    text="↩️ Центр управления",
                    callback_data=owner_callback("menu"),
                )
            ]
        ]
    )


def owner_menu_text(first_name: str = "") -> str:
    greeting = f", {first_name}" if first_name else ""
    return (
        f"<b>Velvet Archive · центр управления</b>{greeting}\n\n"
        "Все основные разделы открываются кнопками. Опасные операции "
        "требуют отдельного подтверждения, а ввод текста используется только "
        "там, где без него действительно нельзя: например, для задачи Codex."
    )


def owner_help_text() -> str:
    return (
        "<b>Как устроено кнопочное управление</b>\n\n"
        "🖼 <b>Архив</b> — публичный просмотр материалов.\n"
        "👥 <b>Персонажи</b> — карточки, категории, вселенные, истории, промты "
        "и переходы к медиа.\n"
        "🛡 <b>Supervisor и Codex</b> — состояние процесса, логи, Git, "
        "перезапуск, откат и задачи Codex.\n"
        "⚙️ <b>Система</b> — база, воркеры, очереди, версия и отчёт.\n"
        "🧬 <b>Контроль качества</b> — дубли, медиасеты и незаполненные данные.\n"
        "💾 <b>Резервные копии</b> — создание, проверка, история и очистка.\n"
        "📊 <b>Аналитика</b> — канал, промты, персонажи, хэштеги и обсуждения.\n"
        "📣 <b>Публикации</b> — черновики, очередь, ошибки и опубликованные посты.\n\n"
        "Операции, зависящие от конкретного сообщения или файла, по-прежнему "
        "начинаются из этого сообщения: сначала выберите или отправьте материал, "
        "затем используйте доступные кнопки его карточки. Резервные slash-команды "
        "сохранены для аварийного доступа, но в обычном меню Telegram не показываются."
    )


__all__ = (
    "OwnerMenuCallback",
    "build_owner_back_keyboard",
    "build_owner_main_keyboard",
    "owner_callback",
    "owner_help_text",
    "owner_menu_text",
)
