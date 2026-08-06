from __future__ import annotations

from html import escape

from aiogram import Bot

from velvet_bot.domains.telegram_storage.librarian_models import (
    LibrarianAnalysis,
    LibrarianObject,
)


class ArthurReportPublisher:
    def __init__(
        self,
        bot: Bot,
        *,
        chat_id: int | None,
        thread_id: int | None,
    ) -> None:
        self._bot = bot
        self._chat_id = chat_id
        self._thread_id = thread_id

    async def publish(
        self,
        item: LibrarianObject,
        analysis: LibrarianAnalysis,
    ) -> None:
        if self._chat_id is None:
            return
        text = (
            "<b>Arthur Librarian · анализ завершён</b>\n\n"
            f"Storage ID: <code>{item.object_id}</code>\n"
            f"Файл: <code>{escape(item.original_name[:180])}</code>\n"
            f"Уверенность: <code>{analysis.confidence}%</code>\n\n"
            f"{escape(analysis.summary[:2500])}\n\n"
            f"Команда: <code>/result {item.object_id}</code>"
        )
        await self._bot.send_message(
            self._chat_id,
            text[:4000],
            message_thread_id=self._thread_id,
            disable_notification=True,
        )

    async def publish_failure(
        self,
        *,
        object_id: int,
        item: LibrarianObject | None,
        error: BaseException,
    ) -> None:
        del item, error
        if self._chat_id is None:
            return
        await self._bot.send_message(
            self._chat_id,
            (
                "<b>Arthur Librarian · анализ не выполнен</b>\n\n"
                f"Storage ID: <code>{object_id}</code>\n"
                "Подробности сохранены в состоянии job без публикации архивного текста."
            ),
            message_thread_id=self._thread_id,
            disable_notification=False,
        )


__all__ = ("ArthurReportPublisher",)
