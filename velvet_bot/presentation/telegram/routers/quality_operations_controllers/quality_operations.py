from __future__ import annotations

from velvet_bot.presentation.telegram.shared import safe_edit_message_text

import asyncio
import io
import logging
from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramNetworkError,
)
from aiogram.filters import BaseFilter
from aiogram.types import (
    CallbackQuery,
    ForceReply,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from velvet_bot.ai_job_runtime import AIJobTracker
from velvet_bot.ai_quality import AIQualityRepository, AIQualitySummary, QualityVisionClient
from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.local_ai_runtime import get_local_ai_lock
from velvet_bot.quality_operations import QualityOperationsRepository, QualityQueuePlan
from velvet_bot.quality_ui import QualityCallback, quality_callback
from velvet_bot.workers import WorkerManager, WorkerSnapshot


router = Router(name=__name__)
logger = logging.getLogger(__name__)

_UPLOAD_MARKER = "VELVET_AI:QUALITY_UPLOAD"
_DOWNLOAD_ATTEMPTS = 3
_DOWNLOAD_TIMEOUT_SECONDS = 90
_RETRY_DELAYS = (1.0, 3.0)

_CHECK_LABELS = {
    "anatomy": "Анатомия",
    "hands": "Руки",
    "face": "Лицо",
    "hair": "Волосы",
    "skin_texture": "Текстура кожи",
    "lighting": "Освещение",
    "exposure": "Экспозиция",
    "sharpness": "Резкость",
    "background": "Фон",
    "reflections": "Отражения",
    "composition": "Композиция",
    "compression": "Сжатие",
    "text_watermarks": "Текст и водяные знаки",
    "ui_artifacts": "Интерфейс и служебные элементы",
}


class QualityUploadReplyFilter(BaseFilter):
    async def __call__(self, message: Message) -> bool:
        reply = message.reply_to_message
        if reply is None:
            return False
        return _UPLOAD_MARKER in (reply.text or reply.caption or "")


def _result_file(message: Message) -> tuple[str, str | None] | None:
    if message.photo:
        photo = message.photo[-1]
        return photo.file_id, photo.file_unique_id
    if message.document and (message.document.mime_type or "").startswith("image/"):
        return message.document.file_id, message.document.file_unique_id
    return None


async def _download_image(bot: Bot, file_id: str) -> bytes:
    errors: list[BaseException] = []
    for attempt in range(1, _DOWNLOAD_ATTEMPTS + 1):
        try:
            destination = io.BytesIO()
            await bot.download(
                file_id,
                destination=destination,
                timeout=_DOWNLOAD_TIMEOUT_SECONDS,
                seek=True,
            )
            value = destination.getvalue()
            if value:
                return value
            errors.append(RuntimeError("Telegram вернул пустой файл."))
        except asyncio.CancelledError:
            raise
        except TelegramBadRequest as error:
            errors.append(error)
            break
        except (TelegramNetworkError, TimeoutError, ConnectionError, OSError) as error:
            errors.append(error)
            if attempt >= _DOWNLOAD_ATTEMPTS:
                break
            await asyncio.sleep(_RETRY_DELAYS[attempt - 1])
        except TelegramAPIError as error:
            errors.append(error)
            break
    if errors:
        raise RuntimeError(f"Не удалось скачать изображение: {errors[-1]}")
    raise RuntimeError("Telegram вернул пустой файл.")


def _list_block(title: str, values: object, emoji: str) -> list[str]:
    if not isinstance(values, list) or not values:
        return []
    lines = ["", f"<b>{emoji} {escape(title)}</b>"]
    for value in values[:8]:
        lines.append(f"• {escape(str(value))}")
    return lines


def _report_text(report: dict[str, object]) -> str:
    verdict = str(report.get("verdict") or "review")
    verdict_label = {
        "ready": "готово к публикации",
        "review": "нужна ручная проверка",
        "critical": "рекомендуется исправление",
    }.get(verdict, verdict)
    emoji = {"ready": "✅", "review": "⚠️", "critical": "🚨"}.get(verdict, "⚠️")
    lines = [
        f"<b>{emoji} Ручная проверка изображения</b>",
        "",
        f"Вердикт: <b>{escape(verdict_label)}</b>",
        f"Качество: <b>{int(report.get('quality_score') or 0)} / 100</b>",
        f"Уверенность Qwen: <b>{int(report.get('confidence') or 0)}%</b>",
        "",
        f"<b>Итог:</b> {escape(str(report.get('summary_ru') or '—'))}",
    ]
    lines.extend(_list_block("Критичные проблемы", report.get("critical_issues"), "🚨"))
    lines.extend(_list_block("Замечания", report.get("warnings"), "⚠️"))
    lines.extend(_list_block("Сильные стороны", report.get("strengths"), "✅"))
    lines.extend(_list_block("Неуверенные области", report.get("uncertain_areas"), "🔎"))
    checks = report.get("checks")
    if isinstance(checks, dict) and checks:
        weakest = sorted(
            (
                (str(key), int(value))
                for key, value in checks.items()
                if isinstance(value, int)
            ),
            key=lambda pair: pair[1],
        )[:7]
        if weakest:
            lines.extend(["", "<b>Слабейшие области:</b>"])
            for key, value in weakest:
                lines.append(f"• {escape(_CHECK_LABELS.get(key, key))}: <b>{value}/100</b>")
    return "\n".join(lines)[:4090]


def _worker_text(worker: WorkerSnapshot | None) -> str:
    if worker is None:
        return "не зарегистрирован"
    if worker.state == "failed":
        return f"ошибка · подряд {worker.consecutive_failures}"
    return f"{worker.state} · успехов {worker.successful_runs} · ошибок {worker.failed_runs}"


def build_quality_operations_menu(
    summary: AIQualitySummary,
    worker: WorkerSnapshot | None,
) -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "<b>🖼 Qwen · проверка архива</b>\n\n"
        "Mass-backfill отключён. Сначала сформируйте точный план, затем "
        "явно подтвердите его запуск.\n\n"
        f"Очередь: <b>{summary.pending + summary.processing}</b> · "
        f"готово <b>{summary.ready}</b>\n"
        f"Без решения: <b>{summary.unreviewed}</b> · "
        f"ошибок/карантина <b>{summary.errors + summary.skipped}</b>\n"
        f"Worker: <code>{escape(_worker_text(worker))}</code>"
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🖼 Новое фото",
                    callback_data=quality_callback("quality_upload"),
                ),
                InlineKeyboardButton(
                    text="📋 Отчёты",
                    callback_data=quality_callback("qchecks", section="review"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="📦 План 10",
                    callback_data=quality_callback("quality_recent", item_id=10),
                ),
                InlineKeyboardButton(
                    text="📦 План 25",
                    callback_data=quality_callback("quality_recent", item_id=25),
                ),
                InlineKeyboardButton(
                    text="▶️ План 100",
                    callback_data=quality_callback("quality_recent", item_id=100),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ Ошибки",
                    callback_data=quality_callback("qchecks", section="errors"),
                ),
                InlineKeyboardButton(
                    text="🔁 Ошибки: план 10",
                    callback_data=quality_callback("quality_retry_errors", item_id=10),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="▶️ Один цикл",
                    callback_data=quality_callback("quality_run"),
                ),
                InlineKeyboardButton(
                    text="🔄 Обновить",
                    callback_data=quality_callback("quality_ops"),
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🛠 Доработка",
                    callback_data=quality_callback("reworks"),
                ),
                InlineKeyboardButton(
                    text="↩️ Qwen",
                    callback_data=quality_callback("ai_menu"),
                ),
            ],
        ]
    )
    return text, keyboard


def _plan_view(plan: QualityQueuePlan) -> tuple[str, InlineKeyboardMarkup]:
    kind_label = "последние изображения" if plan.kind == "recent" else "ошибки/карантин"
    text = (
        "<b>📦 План quality queue</b>\n\n"
        f"План: <code>#{plan.plan_id}</code>\n"
        f"Источник: <b>{escape(kind_label)}</b>\n"
        f"Лимит: <b>{plan.requested_limit}</b>\n"
        f"Выбрано: <b>{plan.selected_count}</b>\n"
        f"Новые: <b>{plan.new_count}</b> · "
        f"legacy pending: <b>{plan.legacy_pending_count}</b> · "
        f"ошибки/карантин: <b>{plan.failed_count}</b>\n\n"
        "План ничего не запускает сам. Подтверждение ниже поставит только "
        "эти media_id в global quality queue. План живёт 15 минут."
    )
    rows: list[list[InlineKeyboardButton]] = []
    if plan.selected_count:
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"▶️ Запустить {plan.selected_count}",
                    callback_data=quality_callback(
                        "quality_plan_start",
                        item_id=plan.plan_id,
                    ),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="↩️ Без запуска",
                callback_data=quality_callback("quality_ops"),
            )
        ]
    )
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def _show_menu(
    message: Message,
    database: Database,
    worker_manager: WorkerManager,
) -> None:
    summary = await AIQualityRepository(database).summary()
    worker = worker_manager.snapshot("ai-quality")
    text, keyboard = build_quality_operations_menu(summary, worker)
    await safe_edit_message_text(
        message,
        text,
        reply_markup=keyboard,
    )


@router.callback_query(QualityCallback.filter(F.action == "quality_ops"))
async def handle_quality_operations_menu(
    callback: CallbackQuery,
    database: Database,
    worker_manager: WorkerManager,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    await _show_menu(callback.message, database, worker_manager)
    await callback.answer()


@router.callback_query(QualityCallback.filter(F.action == "quality_upload"))
async def handle_quality_upload_start(callback: CallbackQuery) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    settings = load_settings()
    if not settings.ai_vision_enabled:
        await callback.answer("Qwen отключён в настройках бота.", show_alert=True)
        return
    await callback.answer()
    await callback.message.answer(
        "<b>🖼 Проверить новое изображение</b>\n\n"
        "Ответьте на это сообщение фотографией или image-файлом. Qwen проверит "
        "анатомию, лицо, руки, кожу, свет, композицию, резкость и артефакты.\n\n"
        f"<code>{_UPLOAD_MARKER}</code>",
        reply_markup=ForceReply(selective=True),
    )


@router.message(QualityUploadReplyFilter())
async def handle_quality_upload_reply(
    message: Message,
    database: Database,
    bot: Bot,
) -> None:
    result_file = _result_file(message)
    if result_file is None:
        await message.answer("Нужно ответить фотографией или image-документом.")
        return
    settings = load_settings()
    if not settings.ai_vision_enabled:
        await message.answer("Qwen отключён в настройках бота.")
        return
    file_id, unique_id = result_file
    tracker = await AIJobTracker.create(
        database=database,
        source_message=message,
        kind="quality_image",
        title="Проверка качества изображения",
        provider=settings.ai_vision_provider,
        model=settings.ai_vision_model,
        request_payload={"file_id": file_id, "file_unique_id": unique_id},
    )
    try:
        await tracker.stage("downloading")
        source = await _download_image(bot, file_id)
        vision_key = settings.ai_vision_api_key
        client = QualityVisionClient(
            provider=settings.ai_vision_provider,
            base_url=settings.ai_vision_base_url,
            model=settings.ai_vision_model,
            api_key=vision_key,
            timeout_seconds=settings.ai_vision_timeout_seconds,
        )
        await tracker.stage("analyzing")
        async with get_local_ai_lock():
            report = await client.analyze(source)
        await tracker.stage("saving")
        rendered = _report_text(report)
        await tracker.ready(result_text=rendered, result_payload=report)
    except asyncio.CancelledError:
        await tracker.error("Задание прервано остановкой процесса.")
        raise
    except Exception as error:  # p2-approved-boundary: compensate-manual-quality-job
        logger.exception("Manual quality analysis failed job_id=%s", tracker.job_id)
        await tracker.error(error)


@router.callback_query(QualityCallback.filter(F.action == "quality_recent"))
async def handle_quality_recent(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    limit = callback_data.item_id if callback_data.item_id in {10, 25, 100} else 25
    plan = await QualityOperationsRepository(database).plan_recent(
        requested_by=callback.from_user.id,
        limit=limit,
    )
    await callback.answer(f"План #{plan.plan_id}: {plan.selected_count} media.")
    text, keyboard = _plan_view(plan)
    await safe_edit_message_text(callback.message, text, reply_markup=keyboard)


@router.callback_query(QualityCallback.filter(F.action == "quality_retry_errors"))
async def handle_quality_retry_errors(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
) -> None:
    if not isinstance(callback.message, Message):
        await callback.answer("Меню больше недоступно.", show_alert=True)
        return
    limit = callback_data.item_id if callback_data.item_id in {10, 25, 100} else 10
    plan = await QualityOperationsRepository(database).plan_errors(
        requested_by=callback.from_user.id,
        limit=limit,
    )
    await callback.answer(f"План #{plan.plan_id}: {plan.selected_count} media.")
    text, keyboard = _plan_view(plan)
    await safe_edit_message_text(callback.message, text, reply_markup=keyboard)


@router.callback_query(QualityCallback.filter(F.action == "quality_plan_start"))
async def handle_quality_plan_start(
    callback: CallbackQuery,
    callback_data: QualityCallback,
    database: Database,
    worker_manager: WorkerManager,
) -> None:
    try:
        count = await QualityOperationsRepository(database).start_plan(
            callback_data.item_id,
            requested_by=callback.from_user.id,
        )
    except ValueError as error:
        await callback.answer(str(error)[:180], show_alert=True)
        return
    await callback.answer(f"В очередь добавлено: {count}.", show_alert=True)
    if isinstance(callback.message, Message):
        await _show_menu(callback.message, database, worker_manager)


@router.callback_query(QualityCallback.filter(F.action == "quality_run"))
async def handle_quality_run(
    callback: CallbackQuery,
    database: Database,
    worker_manager: WorkerManager,
) -> None:
    await callback.answer("Запускаю один цикл проверки качества.")
    try:
        ok = await worker_manager.run_now("ai-quality")
    except (RuntimeError, ValueError) as error:
        if isinstance(callback.message, Message):
            await callback.message.answer(
                "<b>❌ Проверка качества не запущена</b>\n\n"
                f"<code>{escape(str(error))[:900]}</code>"
            )
        return
    if isinstance(callback.message, Message):
        await _show_menu(callback.message, database, worker_manager)
        await callback.message.answer(
            "<b>✅ Цикл проверки качества завершён</b>"
            if ok
            else (
                "<b>❌ Цикл проверки завершился ошибкой</b>\n\n"
                "Подробности находятся в очереди ошибок и центре инцидентов."
            )
        )


__all__ = (
    "QualityUploadReplyFilter",
    "build_quality_operations_menu",
    "router",
)
