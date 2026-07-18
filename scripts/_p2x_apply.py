from pathlib import Path

path = Path("velvet_bot/handlers/publication_center.py")
text = path.read_text(encoding="utf-8")

text = text.replace(
    "from __future__ import annotations\n\nimport re\n",
    "from __future__ import annotations\n\nimport logging\nimport re\n",
    1,
)
text = text.replace(
    "from aiogram.exceptions import TelegramBadRequest\n",
    "from aiogram.exceptions import TelegramAPIError, TelegramBadRequest\n",
    1,
)
text = text.replace(
    "router = Router(name=__name__)\n\n",
    "router = Router(name=__name__)\nlogger = logging.getLogger(__name__)\n\n",
    1,
)

anchor = '''@router.callback_query(PublicationCallback.filter())
async def handle_publication_callback(
'''
helper = '''async def _report_publication_failure(
    *,
    callback: CallbackQuery,
    bot: Bot,
    draft_id: int,
    error: Exception,
) -> None:
    logger.error(
        "Publication failed",
        exc_info=(type(error), error, error.__traceback__),
    )
    text = (
        f"<b>Ошибка публикации №{draft_id}</b>\\n\\n"
        f"<code>{escape(str(error))}</code>"
    )
    if isinstance(callback.message, Message):
        try:
            await callback.message.answer(text)
            return
        except TelegramAPIError as report_error:
            logger.warning(
                "Failed to report publication error in source chat: %s",
                report_error,
            )
    try:
        await bot.send_message(chat_id=callback.from_user.id, text=text)
    except TelegramAPIError as report_error:
        logger.warning(
            "Failed to report publication error privately: %s",
            report_error,
        )


@router.callback_query(PublicationCallback.filter())
async def handle_publication_callback(
'''
if anchor not in text:
    raise SystemExit("callback anchor not found")
text = text.replace(anchor, helper, 1)

old = '''        except Exception as error:
            await callback.message.answer(
                f"<b>Ошибка публикации №{draft.id}</b>\\n\\n"
                f"<code>{escape(str(error))}</code>"
            )
            return
'''
new = '''        except Exception as error:  # p2-approved-boundary: report-publication-failure
            await _report_publication_failure(
                callback=callback,
                bot=bot,
                draft_id=draft.id,
                error=error,
            )
            return
'''
if old not in text:
    raise SystemExit("publish failure block not found")
text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
