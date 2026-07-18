from pathlib import Path

path = Path("velvet_bot/handlers/public_archive.py")
text = path.read_text(encoding="utf-8")


def replace_once(old: str, new: str) -> None:
    global text
    if text.count(old) != 1:
        raise RuntimeError(f"expected one match, found {text.count(old)} for {old[:80]!r}")
    text = text.replace(old, new, 1)


replace_once(
    "from velvet_bot.public_catalog import (\n    get_public_media_state,",
    "from velvet_bot.public_catalog import (\n    PublicMediaState,\n    get_public_media_state,",
)
replace_once(
    "        except Exception:\n            logger.exception(\"Failed to build public image-document preview\")",
    "        except Exception:  # p2-approved-boundary: fallback-public-edit-preview\n            logger.exception(\"Failed to build public image-document preview\")",
)
replace_once(
    "        except Exception:\n            logger.exception(\"Public image preview download failed\")",
    "        except Exception:  # p2-approved-boundary: fallback-public-send-preview\n            logger.exception(\"Public image preview download failed\")",
)

old_like = '''    if action == "like":
        try:
            liked, _ = await toggle_public_like(
                database,
                character_id=page.character.id,
                media_id=page.media.id,
                user_id=callback.from_user.id,
            )
            state = await _load_state(database, page, callback.from_user.id)
            keyboard = build_public_archive_keyboard(
                page,
                state,
                viewer_user_id=callback.from_user.id,
                menu_page=callback_data.page,
                category=callback_data.category,
                universe=callback_data.universe,
                story_id=callback_data.story_id,
            )
            if isinstance(callback.message, Message):
                await callback.message.edit_caption(
                    caption=format_public_archive_caption(page, state),
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            await callback.answer("Отметка поставлена." if liked else "Отметка снята.")
        except Exception:
            logger.exception("Failed to toggle public archive like")
            await callback.answer("Не удалось изменить отметку.", show_alert=True)
        return
'''
new_like = '''    if action == "like":
        try:
            state_before = await _load_state(database, page, callback.from_user.id)
            liked, like_count = await toggle_public_like(
                database,
                character_id=page.character.id,
                media_id=page.media.id,
                user_id=callback.from_user.id,
            )
        except Exception:  # p2-approved-boundary: report-public-like-failure
            logger.exception("Failed to toggle public archive like")
            await callback.answer("Не удалось изменить отметку.", show_alert=True)
            return

        await callback.answer("Отметка поставлена." if liked else "Отметка снята.")
        state = PublicMediaState(
            like_count=like_count,
            liked_by_user=liked,
            subscribed=state_before.subscribed,
        )
        keyboard = build_public_archive_keyboard(
            page,
            state,
            viewer_user_id=callback.from_user.id,
            menu_page=callback_data.page,
            category=callback_data.category,
            universe=callback_data.universe,
            story_id=callback_data.story_id,
        )
        if isinstance(callback.message, Message):
            try:
                await callback.message.edit_caption(
                    caption=format_public_archive_caption(page, state),
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard,
                )
            except TelegramAPIError as error:
                logger.warning(
                    "Public archive like changed but UI refresh failed: %s",
                    error,
                )
        return
'''
replace_once(old_like, new_like)

old_sub = '''    if action == "sub":
        try:
            subscribed = await toggle_character_subscription(
                database,
                character_id=page.character.id,
                user_id=callback.from_user.id,
            )
            state = await _load_state(database, page, callback.from_user.id)
            keyboard = build_public_archive_keyboard(
                page,
                state,
                viewer_user_id=callback.from_user.id,
                menu_page=callback_data.page,
                category=callback_data.category,
                universe=callback_data.universe,
                story_id=callback_data.story_id,
            )
            if isinstance(callback.message, Message):
                await callback.message.edit_reply_markup(reply_markup=keyboard)
            await callback.answer(
                "Подписка включена. Новые материалы придут сюда."
                if subscribed
                else "Подписка отключена.",
                show_alert=True,
            )
        except Exception:
            logger.exception("Failed to toggle character subscription")
            await callback.answer("Не удалось изменить подписку.", show_alert=True)
        return
'''
new_sub = '''    if action == "sub":
        try:
            state_before = await _load_state(database, page, callback.from_user.id)
            subscribed = await toggle_character_subscription(
                database,
                character_id=page.character.id,
                user_id=callback.from_user.id,
            )
        except Exception:  # p2-approved-boundary: report-public-subscription-failure
            logger.exception("Failed to toggle character subscription")
            await callback.answer("Не удалось изменить подписку.", show_alert=True)
            return

        await callback.answer(
            "Подписка включена. Новые материалы придут сюда."
            if subscribed
            else "Подписка отключена.",
            show_alert=True,
        )
        state = PublicMediaState(
            like_count=state_before.like_count,
            liked_by_user=state_before.liked_by_user,
            subscribed=subscribed,
        )
        keyboard = build_public_archive_keyboard(
            page,
            state,
            viewer_user_id=callback.from_user.id,
            menu_page=callback_data.page,
            category=callback_data.category,
            universe=callback_data.universe,
            story_id=callback_data.story_id,
        )
        if isinstance(callback.message, Message):
            try:
                await callback.message.edit_reply_markup(reply_markup=keyboard)
            except TelegramAPIError as error:
                logger.warning(
                    "Character subscription changed but UI refresh failed: %s",
                    error,
                )
        return
'''
replace_once(old_sub, new_sub)

old_download = '''        try:
            await _send_as_document(
                bot=bot, media=page.media, chat_id=PUBLIC_DOWNLOAD_USER_ID
            )
            await callback.answer("Файл отправлен в личный чат.")
        except Exception:
            logger.exception("Failed to send public archive download")
            await callback.answer("Не удалось отправить файл.", show_alert=True)
        return
'''
new_download = '''        try:
            await _send_as_document(
                bot=bot, media=page.media, chat_id=PUBLIC_DOWNLOAD_USER_ID
            )
        except Exception:  # p2-approved-boundary: report-public-download-failure
            logger.exception("Failed to send public archive download")
            await callback.answer("Не удалось отправить файл.", show_alert=True)
            return
        await callback.answer("Файл отправлен в личный чат.")
        return
'''
replace_once(old_download, new_download)

path.write_text(text, encoding="utf-8")
