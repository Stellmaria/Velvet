from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from html import escape

from aiogram import BaseMiddleware, Dispatcher, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    TelegramObject,
    User,
)

from velvet_bot.application.arthur_librarian import (
    ArthurAnalysisOutcome,
    ArthurArchiveStatus,
    ArthurLibrarianApplication,
)
from velvet_bot.core.config.arthur import ArthurSettings
from velvet_bot.domains.telegram_storage.librarian_content import redact_sensitive
from velvet_bot.domains.telegram_storage.librarian_models import StorageLibrarianError

_HELP = """<b>Arthur Librarian</b>

<code>/status</code> — сервисы, модель и очередь
<code>/archive start</code> — запустить полный архивный цикл
<code>/archive stop</code> — мягко остановить архивный цикл
<code>/archive status</code> — состояние архивного цикла
<code>/analyze ID</code> — анализ одного Storage object
<code>/result ID</code> — сохранённый результат
<code>/ask вопрос</code> — ответ по готовому индексу
<code>/digest [дни]</code> — сводка
<code>/queue</code> — состояние очереди
<code>/download ID</code> — исходный объект
<code>/help</code> — ограничения

Env auto-enqueue остаётся выключенным. Архив запускается только явной owner-командой. Vision относится к отдельному gateway scope."""


def _menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/status"), KeyboardButton(text="/queue")],
            [KeyboardButton(text="/archive start"), KeyboardButton(text="/archive stop")],
            [KeyboardButton(text="/archive status"), KeyboardButton(text="/digest 1")],
            [KeyboardButton(text="/help")],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def _caller_allowed(user: User | None, settings: ArthurSettings) -> bool:
    if user is None:
        return False
    if user.id in settings.allowed_user_ids:
        return True
    username = (user.username or "").casefold()
    return bool(username and username in settings.allowed_usernames)


class ArthurOwnerMiddleware(BaseMiddleware):
    def __init__(self, settings: ArthurSettings) -> None:
        self._settings = settings

    async def __call__(
        self,
        handler: Callable[
            [TelegramObject, dict[str, object]], Awaitable[object]
        ],
        event: TelegramObject,
        data: dict[str, object],
    ) -> object:
        user = getattr(event, "from_user", None)
        if _caller_allowed(user, self._settings):
            return await handler(event, data)
        answer = getattr(event, "answer", None)
        if callable(answer):
            await answer("Arthur доступен только владельцу.")
        return None


def _positive_id(message: Message) -> int | None:
    text = message.text or ""
    _, _, raw = text.partition(" ")
    try:
        value = int(raw.strip())
    except ValueError:
        return None
    return value if value > 0 else None


def _command_argument(message: Message) -> str:
    _, _, raw = (message.text or "").partition(" ")
    return raw.strip().casefold()


def _safe_error(error: BaseException) -> str:
    return escape(redact_sensitive(str(error))[:1200] or type(error).__name__)


def _render_outcome(outcome: ArthurAnalysisOutcome) -> str:
    job = outcome.job or {}
    analysis = outcome.analysis
    status = escape(str(job.get("status") or "unknown"))
    lines = [
        "<b>Arthur · Storage result</b>",
        "",
        f"Storage ID: <code>{outcome.object_id}</code>",
        f"Job: <code>{status}</code>",
    ]
    if analysis:
        lines.extend(
            [
                f"Analyzer: <code>{escape(str(analysis.get('analyzer_version') or 'unknown'))}</code>",
                f"Confidence: <code>{escape(str(analysis.get('confidence') or 0))}%</code>",
                "",
                escape(str(analysis.get("summary") or "")[:2600]),
            ]
        )
    elif job.get("last_error"):
        lines.extend(("", "Ошибка: " + escape(str(job["last_error"])[:1200])))
    return "\n".join(lines)[:4000]


def _render_archive_status(status: ArthurArchiveStatus) -> str:
    state = "stopping" if status.stopping else "running" if status.active else "stopped"
    counts = status.counts
    lines = [
        "<b>Arthur · archive</b>",
        "",
        f"State: <code>{state}</code>",
        f"Analyzer: <code>{escape(status.analyzer_version)}</code>",
        f"Queued now (live backlog): <code>{counts.get('queued', 0)}</code>",
        f"Running now: <code>{counts.get('running', 0)}</code>",
        f"Completed total: <code>{counts.get('completed', 0)}</code>",
        f"Skipped total: <code>{counts.get('skipped', 0)}</code>",
        f"Failed total: <code>{counts.get('failed', 0)}</code>",
    ]
    if status.last_error:
        lines.extend(("", "Последняя ошибка: " + escape(status.last_error)))
    return "\n".join(lines)[:4000]


def _register_archive_commands(router: Router) -> None:
    @router.message(Command("archive"))
    async def archive(
        message: Message,
        arthur_app: ArthurLibrarianApplication,
    ) -> None:
        action = _command_argument(message) or "status"
        try:
            if action == "start":
                started = await arthur_app.start_archive()
                status = await arthur_app.archive_status()
                prefix = (
                    "Архивный анализ запущен."
                    if started
                    else "Архивный анализ уже запущен."
                )
                await message.answer(prefix + "\n\n" + _render_archive_status(status))
                return
            if action == "stop":
                stopping = await arthur_app.stop_archive()
                status = await arthur_app.archive_status()
                prefix = (
                    "Остановка запрошена. Текущий объект будет завершён."
                    if stopping
                    else "Архивный анализ уже остановлен."
                )
                await message.answer(prefix + "\n\n" + _render_archive_status(status))
                return
            if action == "status":
                await message.answer(
                    _render_archive_status(await arthur_app.archive_status())
                )
                return
        except StorageLibrarianError as error:
            await message.answer("Arthur archive недоступен: " + _safe_error(error))
            return
        await message.answer(
            "Формат: <code>/archive start</code>, <code>/archive stop</code> "
            "или <code>/archive status</code>"
        )


def build_arthur_router() -> Router:
    router = Router(name="arthur-librarian")
    _register_archive_commands(router)

    @router.message(Command("start"))
    async def start(message: Message) -> None:
        await message.answer(
            "<b>Arthur Librarian</b>\n\n"
            "Отдельный owner-only интерфейс локального Storage analysis. "
            "Массовый архив запускается только явной командой владельца.",
            reply_markup=_menu(),
        )

    @router.message(Command("help"))
    async def help_command(message: Message) -> None:
        await message.answer(_HELP, reply_markup=_menu())

    @router.message(Command("status"))
    async def status(
        message: Message,
        arthur_app: ArthurLibrarianApplication,
    ) -> None:
        counts, health, archive = await asyncio.gather(
            arthur_app.queue_counts(),
            arthur_app.service_health(),
            arthur_app.archive_status(),
        )
        settings = arthur_app.librarian_settings
        archive_state = (
            "stopping" if archive.stopping else "running" if archive.active else "stopped"
        )
        await message.answer(
            "<b>Arthur status</b>\n\n"
            f"Gateway: <code>{'ok' if health.gateway else 'unavailable'}</code>\n"
            f"Ollama: <code>{'ok' if health.ollama else 'unavailable'}</code>\n"
            f"Text alias: <code>{'loaded' if health.text_model else 'missing'}</code>\n"
            f"Hermes: <code>{'ok' if health.hermes else 'unavailable'}</code>\n"
            f"Librarian: <code>{'enabled' if settings.enabled else 'disabled'}</code>\n"
            f"Text model: <code>{escape(settings.text_model)}</code>\n"
            f"Analyzer: <code>{escape(settings.analyzer_version)}</code>\n"
            "Env auto enqueue: <code>false</code>\n"
            f"Archive: <code>{archive_state}</code>\n"
            f"Queued: <code>{counts.get('queued', 0)}</code>\n"
            f"Running: <code>{counts.get('running', 0)}</code>\n"
            f"Failed: <code>{counts.get('failed', 0)}</code>"
        )

    @router.message(Command("queue"))
    async def queue(
        message: Message,
        arthur_app: ArthurLibrarianApplication,
    ) -> None:
        counts = await arthur_app.queue_counts()
        body = "\n".join(
            f"{escape(name)}: <code>{value}</code>"
            for name, value in sorted(counts.items())
        )
        await message.answer("<b>Storage queue</b>\n\n" + body)

    @router.message(Command("analyze"))
    async def analyze(
        message: Message,
        arthur_app: ArthurLibrarianApplication,
    ) -> None:
        object_id = _positive_id(message)
        if object_id is None:
            await message.answer("Формат: <code>/analyze ID</code>")
            return
        settings = arthur_app.librarian_settings
        status_message = await message.answer(
            "<b>Arthur · manual analysis</b>\n\n"
            f"Storage ID: <code>{object_id}</code>\n"
            f"Model: <code>{escape(settings.text_model)}</code>\n"
            "Mode: <code>manual-first</code>\n"
            "Status: <code>running</code>"
        )
        try:
            outcome = await arthur_app.analyze(object_id)
        except (
            StorageLibrarianError,
            TelegramAPIError,
            TimeoutError,
            OSError,
        ) as error:
            await status_message.edit_text(
                "<b>Arthur · analysis failed</b>\n\n"
                f"Storage ID: <code>{object_id}</code>\n"
                f"Ошибка: {_safe_error(error)}"
            )
            return
        await status_message.edit_text(_render_outcome(outcome))

    @router.message(Command("result"))
    async def result(
        message: Message,
        arthur_app: ArthurLibrarianApplication,
    ) -> None:
        object_id = _positive_id(message)
        if object_id is None:
            await message.answer("Формат: <code>/result ID</code>")
            return
        await message.answer(_render_outcome(await arthur_app.result(object_id)))

    @router.message(Command("ask"))
    async def ask(
        message: Message,
        arthur_app: ArthurLibrarianApplication,
    ) -> None:
        _, _, question = (message.text or "").partition(" ")
        question = question.strip()
        if not question:
            await message.answer("Формат: <code>/ask вопрос</code>")
            return
        try:
            answer = await arthur_app.ask(question)
        except (
            StorageLibrarianError,
            TelegramAPIError,
            TimeoutError,
            OSError,
        ) as error:
            await message.answer("Arthur не ответил: " + _safe_error(error))
            return
        await message.answer(escape(answer)[:4000])

    @router.message(Command("digest"))
    async def digest(
        message: Message,
        arthur_app: ArthurLibrarianApplication,
    ) -> None:
        _, _, raw = (message.text or "").partition(" ")
        try:
            days = max(1, min(int(raw.strip() or "1"), 365))
        except ValueError:
            await message.answer("Формат: <code>/digest [дни]</code>")
            return
        rows = await arthur_app.digest(days)
        if not rows:
            await message.answer("За выбранный период анализов нет.")
            return
        lines = [f"<b>Arthur digest · {days} дн.</b>", ""]
        for row in rows:
            lines.append(
                f"• <code>#{int(row['storage_object_id'])}</code> "
                + escape(str(row.get("summary") or "")[:240])
            )
        await message.answer("\n".join(lines)[:4000])

    @router.message(Command("download"))
    async def download(
        message: Message,
        arthur_app: ArthurLibrarianApplication,
    ) -> None:
        object_id = _positive_id(message)
        if object_id is None:
            await message.answer("Формат: <code>/download ID</code>")
            return
        try:
            item, payload = await arthur_app.download(object_id)
        except (
            StorageLibrarianError,
            TelegramAPIError,
            TimeoutError,
            OSError,
        ) as error:
            await message.answer("Файл недоступен: " + _safe_error(error))
            return
        await message.answer_document(
            BufferedInputFile(payload, filename=item.original_name),
            caption=f"Storage <code>#{item.object_id}</code>",
        )

    return router


def build_arthur_dispatcher(
    *,
    settings: ArthurSettings,
    application: ArthurLibrarianApplication,
) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.workflow_data["arthur_app"] = application
    middleware = ArthurOwnerMiddleware(settings)
    dispatcher.message.outer_middleware(middleware)
    dispatcher.callback_query.outer_middleware(middleware)
    dispatcher.include_router(build_arthur_router())
    return dispatcher


__all__ = (
    "ArthurOwnerMiddleware",
    "build_arthur_dispatcher",
    "build_arthur_router",
)
