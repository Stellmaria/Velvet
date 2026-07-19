from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.handlers.admin_directory import AdminDirectoryCallback
from velvet_bot.handlers.analytics_dashboard import AnalyticsCallback
from velvet_bot.handlers.backup_center import BackupCallback
from velvet_bot.handlers.publication_center import PublicationCallback
from velvet_bot.owner_callbacks import (
    OwnerMenuCallback,
    owner_action_callback,
    owner_callback,
)
from velvet_bot.presentation.telegram.routers.supervisor.control import SupervisorCallback
from velvet_bot.presentation.telegram.routers.system import SystemCallback
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.quality_ui import quality_callback
from velvet_bot.watermark_ui import WatermarkCallback


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
                    text="💧 Водяной знак",
                    callback_data=WatermarkCallback(action="start").pack(),
                ),
                InlineKeyboardButton(
                    text="🧰 Все действия",
                    callback_data=owner_action_callback("menu"),
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
                    text="🤖 Velvet AI",
                    callback_data=quality_callback("ai_menu"),
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
        "💧 <b>Водяной знак</b> — отправка изображения в локальную Krita, "
        "preview, выбор угла, цвета, прозрачности, размера и отступа.\n"
        "🧰 <b>Все действия</b> — формы создания персонажей, тем, историй, "
        "референсов, алиасов, сохранения медиа и импорта.\n"
        "🛡 <b>Supervisor и Codex</b> — состояние процесса, логи, Git, "
        "перезапуск, откат и задачи Codex.\n"
        "⚙️ <b>Система</b> — база, воркеры, очереди, версия и отчёт.\n"
        "🤖 <b>Velvet AI</b> — качество, референсы, промт против результата, "
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
