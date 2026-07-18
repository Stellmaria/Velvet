from pathlib import Path

path = Path("velvet_bot/handlers/public_manager.py")
text = path.read_text(encoding="utf-8")
old = '''    if action == "download":
        try:
            if isinstance(bot, ProtectedMediaBot):
                bot.allow_unprotected_private_user(viewer_user_id)
            await _send_as_document(
                bot=bot,
                media=page.media,
                chat_id=viewer_user_id,
            )
            await callback.answer("Оригинал отправлен в личный чат.")
        except Exception:
            logger.exception("Failed to send archive original to manager")
            await callback.answer("Не удалось отправить оригинал.", show_alert=True)
        return
'''
new = '''    if action == "download":
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
'''
if text.count(old) != 1:
    raise RuntimeError(f"expected one manager download block, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
