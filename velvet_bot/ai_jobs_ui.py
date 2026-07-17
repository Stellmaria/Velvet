from __future__ import annotations

from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from velvet_bot.ai_jobs import AIJob, AIJobPage
from velvet_bot.quality_ui import quality_callback


KIND_LABELS = {
    "quality_image": "Проверка качества изображения",
    "reference_comparison": "Сравнение с референсом",
    "prompt_result": "Промт против результата",
    "palette_composition": "Палитра и композиция",
    "velvet_formatting": "Оформление Velvet Anatomy",
    "media_set_consistency": "Целостность медиасета",
}
STATUS_LABELS = {
    "pending": "в очереди",
    "processing": "выполняется",
    "ready": "готово",
    "error": "ошибка",
}
STATUS_ICONS = {
    "pending": "🕓",
    "processing": "🧠",
    "ready": "✅",
    "error": "❌",
}
STAGE_LABELS = {
    "queued": "запрос зарегистрирован",
    "downloading": "скачивание файлов",
    "preparing": "подготовка данных",
    "analyzing": "анализ Qwen",
    "saving": "сохранение результата",
    "completed": "результат сохранён",
    "failed": "задача завершилась ошибкой",
    "interrupted": "задача прервана",
}
REPEAT_ACTIONS = {
    "quality_image": "quality_upload",
    "reference_comparison": "refcompare_start",
    "prompt_result": "promptcheck_start",
    "palette_composition": "visual_start",
    "velvet_formatting": "format_menu",
    "media_set_consistency": "setreports",
}


def _timestamp(job: AIJob) -> str:
    return job.created_at.astimezone().strftime("%d.%m.%Y %H:%M")


def build_job_progress_text(job: AIJob) -> str:
    kind = KIND_LABELS.get(job.kind, job.title)
    status = STATUS_LABELS.get(job.status, job.status)
    stage = STAGE_LABELS.get(job.stage, job.stage)
    lines = [
        f"<b>{STATUS_ICONS.get(job.status, 'ℹ️')} AI-задание #{job.id}</b>",
        "",
        f"Тип: <b>{escape(kind)}</b>",
        f"Статус: <b>{escape(status)}</b>",
        f"Этап: <b>{escape(stage)}</b>",
        f"Создано: <b>{escape(_timestamp(job))}</b>",
    ]
    if job.provider or job.model:
        lines.extend(
            [
                "",
                f"Провайдер: <code>{escape(job.provider or '—')}</code>",
                f"Модель: <code>{escape(job.model or '—')}</code>",
            ]
        )
    if job.status in {"pending", "processing"}:
        lines.extend(
            [
                "",
                "Задание сохранено в базе. Экран можно закрыть и позже открыть его из истории.",
            ]
        )
    elif job.status == "error":
        lines.extend(
            [
                "",
                "<b>Причина:</b>",
                f"<code>{escape(job.error_message or 'Причина не сохранена.')[:1800]}</code>",
            ]
        )
    return "\n".join(lines)[:4090]


def build_job_detail_text(job: AIJob) -> str:
    if job.status == "ready" and job.result_text:
        prefix = (
            f"<b>✅ AI-задание #{job.id} · результат сохранён</b>\n"
            f"<i>{escape(KIND_LABELS.get(job.kind, job.title))}</i>\n\n"
        )
        available = max(0, 4090 - len(prefix))
        return prefix + job.result_text[:available]
    return build_job_progress_text(job)


def build_job_keyboard(job: AIJob, *, page: int = 0) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if job.status in {"pending", "processing"}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔄 Обновить статус",
                    callback_data=quality_callback("aijob", page=page, item_id=job.id),
                )
            ]
        )
    repeat_action = REPEAT_ACTIONS.get(job.kind)
    if repeat_action and job.status in {"ready", "error"}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔁 Запустить ещё раз",
                    callback_data=quality_callback(repeat_action),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="📋 История AI",
                callback_data=quality_callback("aijobs", page=page),
            ),
            InlineKeyboardButton(
                text="↩️ Velvet AI",
                callback_data=quality_callback("ai_menu"),
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_job_list(page: AIJobPage) -> tuple[str, InlineKeyboardMarkup]:
    lines = [
        "<b>📋 История AI-заданий</b>",
        "",
        f"Всего: <b>{page.total_items}</b>",
        f"Страница: <b>{page.page + 1}</b> из <b>{page.total_pages}</b>",
        "",
        "Здесь видно, был ли запрос принят, выполняется ли он, завершён ли результатом или ошибкой.",
    ]
    rows: list[list[InlineKeyboardButton]] = []
    for job in page.items:
        label = KIND_LABELS.get(job.kind, job.title)
        rows.append(
            [
                InlineKeyboardButton(
                    text=(
                        f"{STATUS_ICONS.get(job.status, 'ℹ️')} #{job.id} · "
                        f"{label[:35]}"
                    )[:64],
                    callback_data=quality_callback("aijob", page=page.page, item_id=job.id),
                )
            ]
        )
    if page.total_pages > 1:
        rows.append(
            [
                InlineKeyboardButton(
                    text="◀️",
                    callback_data=quality_callback(
                        "aijobs", page=(page.page - 1) % page.total_pages
                    ),
                ),
                InlineKeyboardButton(
                    text=f"{page.page + 1} / {page.total_pages}",
                    callback_data=quality_callback("noop"),
                ),
                InlineKeyboardButton(
                    text="▶️",
                    callback_data=quality_callback(
                        "aijobs", page=(page.page + 1) % page.total_pages
                    ),
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text="🔄 Обновить",
                callback_data=quality_callback("aijobs", page=page.page),
            ),
            InlineKeyboardButton(
                text="↩️ Velvet AI",
                callback_data=quality_callback("ai_menu"),
            ),
        ]
    )
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


__all__ = (
    "KIND_LABELS",
    "build_job_detail_text",
    "build_job_keyboard",
    "build_job_list",
    "build_job_progress_text",
)
