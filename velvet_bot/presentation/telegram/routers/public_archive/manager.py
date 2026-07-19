from __future__ import annotations

import io
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from velvet_bot.access import AccessPolicy
from velvet_bot.archive_catalog import (
    ArchivedMedia,
    delete_archive_item,
    get_archive_page,
    toggle_archive_media_spoiler,
)
from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.character_directory import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    UNIVERSE_LABELS,
    UNIVERSE_ORDER,
    get_character_directory_item,
    set_character_category,
    set_character_universe,
)
from velvet_bot.database import Database
from velvet_bot.presentation.telegram.message_deletion import (
    delete_message_idempotently,
)
from velvet_bot.protected_bot import ProtectedMediaBot
from velvet_bot.public_archive_display import (
    refresh_viewer_archive_caption,
    replace_viewer_archive_page,
)
from velvet_bot.public_manager_access import has_public_manager_access
from velvet_bot.public_manager_ui import (
    build_manager_category_picker,
    build_manager_delete_confirmation,
    build_manager_story_picker,
    build_manager_universe_picker,
)
from velvet_bot.public_ui import PublicArchiveCallback
from velvet_bot.story_catalog import (
    list_story_page,
    set_character_story,
    universe_requires_story,
)

router = Router(name=__name__)
logger = logging.getLogger(__name__)


_ACTIONS = {
    "download", "pback", "psp", "pcats", "pcat", "punis", "puni",
    "psts", "pstp", "pst", "pdel", "pdelok", "pdelno", "pnoop",
}


async def _send_as_document(
    *,
    bot: Bot,
    media: ArchivedMedia,
    chat_id: int,
) -> Message:
    if media.media_type == "document":
        return await bot.send_document(
            chat_id=chat_id,
            document=media.telegram_file_id,
            caption="Оригинал из Velvet Archive",
        )
    destination = io.BytesIO()
    await bot.download(media.telegram_file_id, destination=destination, seek=True)
    payload = destination.getvalue()
    if not payload:
        raise RuntimeError("Telegram вернул пустой файл.")
    return await bot.send_document(
        chat_id=chat_id,
        document=BufferedInputFile(payload, filename=media.display_file_name),
        caption="Оригинал из Velvet Archive",
    )


async def _show_story_picker(
    callback: CallbackQuery,
    database: Database,
    *,
    character_id: int,
    offset: int,
    page_number: int,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    archive_page = await get_archive_page(database, character_id, offset)
    item = await get_character_directory_item(database, character_id)
    if archive_page is None or archive_page.media is None or item is None:
        await callback.answer("Персонаж или материал больше не найден.", show_alert=True)
        return
    if not item.universe:
        await callback.answer("Сначала выберите вселенную.", show_alert=True)
        return
    story_page = await list_story_page(
        database,
        universe=item.universe,
        page=page_number,
    )
    if not story_page.items:
        await callback.answer("В этой вселенной нет историй.", show_alert=True)
        return
    await callback.message.edit_caption(
        caption=(
            "<b>Изменить историю</b>\n\n"
            f"Персонаж: <b>{escape(archive_page.character.name)}</b>\n"
            f"Вселенная: <b>{escape(UNIVERSE_LABELS[item.universe])}</b>\n"
            f"Страница: <b>{story_page.page + 1}</b> из "
            f"<b>{story_page.total_pages}</b>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=build_manager_story_picker(archive_page, story_page),
    )


@router.callback_query(
    PublicArchiveCallback.filter(F.action.in_(_ACTIONS)),
)
async def handle_public_manager(
    callback: CallbackQuery,
    callback_data: PublicArchiveCallback,
    database: Database,
    bot: Bot,
    access_policy: AccessPolicy,
    audit_logger: TelegramAuditLogger | None = None,
) -> None:
    if not has_public_manager_access(callback.from_user, access_policy):
        await callback.answer("Управление архивом для вас закрыто.", show_alert=True)
        return

    viewer_user_id = callback.from_user.id
    action = callback_data.action
    if action == "pnoop":
        await callback.answer()
        return

    page = await get_archive_page(
        database,
        callback_data.character_id,
        callback_data.offset,
    )
    if page is None or page.media is None:
        await callback.answer("Материал больше недоступен.", show_alert=True)
        return

    if action == "download":
        try:
            if isinstance(bot, ProtectedMediaBot):
                bot.allow_unprotected_private_user(viewer_user_id)
            await _send_as_document(
                bot=bot,
                media=page.media,
                chat_id=viewer_user_id,
            )
        except Exception:  # p2-approved-boundary: report-manager-download-failure
            logger.exception("Failed to send archive original to manager")
            await callback.answer("Не удалось отправить оригинал.", show_alert=True)
            return
        await callback.answer("Оригинал отправлен в личный чат.")
        return

    if action in {"pback", "pdelno"}:
        await refresh_viewer_archive_caption(
            callback=callback,
            database=database,
            page=page,
            viewer_user_id=viewer_user_id,
            manager_access=True,
        )
        await callback.answer()
        return

    if action == "psp":
        enabled = await toggle_archive_media_spoiler(
            database,
            character_id=page.character.id,
            media_id=page.media.id,
        )
        if enabled is None:
            await callback.answer("Материал больше недоступен.", show_alert=True)
            return
        updated_page = await get_archive_page(database, page.character.id, page.offset)
        if updated_page is None or updated_page.media is None:
            await callback.answer("Материал больше недоступен.", show_alert=True)
            return
        await replace_viewer_archive_page(
            callback=callback,
            bot=bot,
            database=database,
            page=updated_page,
            viewer_user_id=viewer_user_id,
            manager_access=True,
        )
        await callback.answer(
            "Спойлер включён." if enabled else "Спойлер снят.",
            show_alert=True,
        )
        return

    if action == "pcats":
        if isinstance(callback.message, Message):
            await callback.message.edit_caption(
                caption=(
                    "<b>Изменить пол / состав</b>\n\n"
                    f"Персонаж: <b>{escape(page.character.name)}</b>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=build_manager_category_picker(page),
            )
        await callback.answer()
        return

    if action == "pcat":
        if callback_data.category not in CATEGORY_ORDER:
            await callback.answer("Неизвестная категория.", show_alert=True)
            return
        await set_character_category(
            database,
            character_id=page.character.id,
            category=callback_data.category,
        )
        await refresh_viewer_archive_caption(
            callback=callback,
            database=database,
            page=page,
            viewer_user_id=viewer_user_id,
            manager_access=True,
        )
        await callback.answer(
            f"Категория: {CATEGORY_LABELS[callback_data.category]}",
            show_alert=True,
        )
        return

    if action == "punis":
        if isinstance(callback.message, Message):
            await callback.message.edit_caption(
                caption=(
                    "<b>Изменить вселенную</b>\n\n"
                    f"Персонаж: <b>{escape(page.character.name)}</b>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=build_manager_universe_picker(page),
            )
        await callback.answer()
        return

    if action == "puni":
        if callback_data.universe not in UNIVERSE_ORDER:
            await callback.answer("Неизвестная вселенная.", show_alert=True)
            return
        await set_character_universe(
            database,
            character_id=page.character.id,
            universe=callback_data.universe,
        )
        if universe_requires_story(callback_data.universe):
            await _show_story_picker(
                callback,
                database,
                character_id=page.character.id,
                offset=page.offset,
                page_number=0,
            )
            await callback.answer(
                "Вселенная изменена. Выберите историю.",
                show_alert=True,
            )
        else:
            await refresh_viewer_archive_caption(
                callback=callback,
                database=database,
                page=page,
                viewer_user_id=viewer_user_id,
                manager_access=True,
            )
            await callback.answer(
                f"Вселенная: {UNIVERSE_LABELS[callback_data.universe]}",
                show_alert=True,
            )
        return

    if action in {"psts", "pstp"}:
        await _show_story_picker(
            callback,
            database,
            character_id=page.character.id,
            offset=page.offset,
            page_number=callback_data.page,
        )
        await callback.answer()
        return

    if action == "pst":
        await set_character_story(
            database,
            character_id=page.character.id,
            story_id=callback_data.story_id,
        )
        await refresh_viewer_archive_caption(
            callback=callback,
            database=database,
            page=page,
            viewer_user_id=viewer_user_id,
            manager_access=True,
        )
        await callback.answer("История изменена.", show_alert=True)
        return

    if action == "pdel":
        if isinstance(callback.message, Message):
            await callback.message.edit_caption(
                caption=(
                    "<b>Удалить материал из архива?</b>\n\n"
                    f"Персонаж: <b>{escape(page.character.name)}</b>\n"
                    f"Файл: <code>{escape(page.media.display_file_name)}</code>"
                ),
                parse_mode=ParseMode.HTML,
                reply_markup=build_manager_delete_confirmation(page),
            )
        await callback.answer()
        return

    if action == "pdelok":
        deleted = await delete_archive_item(
            database,
            page.character.id,
            callback_data.media_id or page.media.id,
        )
        if deleted is None:
            await callback.answer("Материал уже удалён.", show_alert=True)
            return
        topic_delete_state = "not_requested"
        if deleted.media.archive_message_id and deleted.character.archive_chat_id:
            try:
                topic_delete_state = await delete_message_idempotently(
                    bot,
                    chat_id=deleted.character.archive_chat_id,
                    message_id=deleted.media.archive_message_id,
                )
            except TelegramAPIError as error:
                topic_delete_state = "failed"
                logger.warning("Could not delete archive topic message: %s", error)
        if audit_logger is not None:
            await audit_logger.send(
                "Медиа удалено через открытый архив",
                level="SUCCESS",
                character=deleted.character.name,
                media_id=deleted.media.id,
                deleted_by=viewer_user_id,
                remaining=deleted.remaining_total,
                topic_message_deleted=topic_delete_state == "deleted",
                topic_message_already_absent=topic_delete_state == "already_absent",
                topic_message_delete_failed=topic_delete_state == "failed",
            )
        if not isinstance(callback.message, Message):
            await callback.answer("Удалено.", show_alert=True)
            return
        if deleted.remaining_total == 0:
            try:
                await callback.message.delete()
            except TelegramBadRequest:
                pass
            await callback.answer("Удалено. Архив пуст.", show_alert=True)
            return
        next_page = await get_archive_page(
            database,
            page.character.id,
            min(page.offset, deleted.remaining_total - 1),
        )
        if next_page is None or next_page.media is None:
            await callback.message.delete()
            await callback.answer("Удалено.", show_alert=True)
            return
        await replace_viewer_archive_page(
            callback=callback,
            bot=bot,
            database=database,
            page=next_page,
            viewer_user_id=viewer_user_id,
            manager_access=True,
        )
        await callback.answer("Материал удалён.", show_alert=True)
