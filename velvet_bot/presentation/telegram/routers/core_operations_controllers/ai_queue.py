from __future__ import annotations

from decimal import Decimal
from html import escape
from uuid import UUID

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from velvet_bot.core.config import load_settings
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import (
    AITask,
    AITaskQueueService,
    AITaskQueueSnapshot,
    AITaskStatus,
    AIUsageService,
)
from velvet_bot.domains.vision_batches import (
    VisionBatchError,
    VisionBatchProgress,
    VisionBatchStatus,
    build_vision_batch_service,
)

router = Router(name=__name__)
_MAX_RECENT_TASKS = 15


def _format_rub(value: Decimal) -> str:
    rendered = f"{value.quantize(Decimal('0.01')):,.2f}"
    return rendered.replace(",", " ").replace(".", ",") + " ₽"


def _arguments(message: Message) -> str:
    text = (message.text or "").strip()
    _, separator, tail = text.partition(" ")
    return tail.strip() if separator else ""


def _limit(message: Message) -> int:
    value = _arguments(message)
    if not value:
        return 8
    try:
        return max(1, min(int(value), _MAX_RECENT_TASKS))
    except ValueError:
        return 8


def _batch_limit(message: Message) -> int:
    value = _arguments(message)
    if not value:
        return 100
    try:
        return max(1, min(int(value), 5000))
    except ValueError:
        return 100


def _parse_task_id(value: str) -> UUID | None:
    try:
        return UUID(value.strip())
    except (ValueError, AttributeError):
        return None


def _status_icon(status: AITaskStatus) -> str:
    return {
        AITaskStatus.QUEUED: "⏳",
        AITaskStatus.RUNNING: "⚙️",
        AITaskStatus.SUCCESS: "✅",
        AITaskStatus.ERROR: "❌",
        AITaskStatus.CANCELLED: "🚫",
    }[status]


def _batch_status_icon(status: VisionBatchStatus) -> str:
    return {
        VisionBatchStatus.PLANNED: "🧾",
        VisionBatchStatus.STARTING: "🚀",
        VisionBatchStatus.QUEUED: "⏳",
        VisionBatchStatus.COMPLETED: "✅",
        VisionBatchStatus.CANCELLED: "🚫",
        VisionBatchStatus.EXPIRED: "⌛",
        VisionBatchStatus.ERROR: "❌",
    }[status]


def _short(value: str, *, limit: int) -> str:
    cleaned = " ".join(value.split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


def _snapshot_text(snapshot: AITaskQueueSnapshot) -> str:
    runtime = "приостановлен" if snapshot.paused else "работает"
    lines = [
        "<b>🧠 Очередь AI-задач</b>",
        "",
        f"Контур: <b>{runtime}</b>",
        f"Активных: <b>{snapshot.active}</b>",
        f"В очереди: {snapshot.queued}",
        f"Выполняются: {snapshot.running}",
        f"Успешно: {snapshot.success}",
        f"Ошибки: {snapshot.error}",
        f"Отменены: {snapshot.cancelled}",
    ]
    if snapshot.paused and snapshot.pause_reason:
        lines.append(f"Причина паузы: <code>{escape(snapshot.pause_reason)}</code>")
    return "\n".join(lines)


def _task_text(task: AITask) -> str:
    time_text = task.updated_at.strftime("%d.%m %H:%M")
    attempt_text = f"{task.attempt_count}/{task.max_attempts}"
    lock_text = (
        f" · worker <code>{escape(_short(task.locked_by, limit=24))}</code>"
        if task.locked_by
        else ""
    )
    retry_text = (
        f" · retry {task.last_retry_delay_seconds} сек."
        if task.last_retry_delay_seconds is not None
        else ""
    )
    error_text = (
        f"\n   Ошибка: <code>{escape(_short(task.last_error or task.last_error_type or '', limit=120))}</code>"
        if task.last_error or task.last_error_type
        else ""
    )
    return (
        f"{_status_icon(task.status)} <b>{escape(task.scope.value)}</b> · "
        f"<code>{escape(_short(task.task_type, limit=42))}</code>\n"
        f"   ID: <code>{task.id}</code>\n"
        f"   priority {task.priority} · попытка {attempt_text} · "
        f"{_format_rub(task.estimated_cost_rub)} · {time_text}{lock_text}{retry_text}"
        f"{error_text}"
    )


def _batch_text(progress: VisionBatchProgress) -> str:
    plan = progress.plan
    expires = plan.expires_at.strftime("%d.%m %H:%M")
    lines = [
        f"<b>{_batch_status_icon(plan.status)} VL-партия</b>",
        f"ID: <code>{plan.id}</code>",
        f"Статус: <b>{escape(plan.status.value)}</b>",
        f"Кандидатов: <b>{plan.candidate_count}</b>",
        f"Создано задач: {plan.created_task_count}",
        f"Дедуплицировано: {plan.deduplicated_task_count}",
        f"Максимум на изображение: {_format_rub(plan.max_cost_per_item_rub)}",
        f"Максимум партии: <b>{_format_rub(plan.estimated_cost_rub)}</b>",
        f"Истекает: {expires}",
    ]
    if plan.status in {
        VisionBatchStatus.QUEUED,
        VisionBatchStatus.COMPLETED,
        VisionBatchStatus.CANCELLED,
        VisionBatchStatus.ERROR,
    }:
        lines.extend(
            [
                "",
                f"В очереди: {progress.queued}",
                f"Выполняются: {progress.running}",
                f"Успешно: {progress.success}",
                f"Ошибки: {progress.error}",
                f"Отменены: {progress.cancelled}",
            ]
        )
    if plan.last_error:
        lines.append(
            f"\nПричина: <code>{escape(_short(plan.last_error, limit=300))}</code>"
        )
    return "\n".join(lines)


def _owner_id(message: Message) -> int | None:
    return int(message.from_user.id) if message.from_user is not None else None


@router.message(Command("ai_queue"))
async def handle_ai_queue(
    message: Message,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    snapshot = await ai_task_queue_service.snapshot()
    tasks = await ai_task_queue_service.recent(limit=_limit(message))
    sections = [_snapshot_text(snapshot)]
    if tasks:
        sections.append(
            "<b>Последние задачи</b>\n\n"
            + "\n\n".join(_task_text(task) for task in tasks)
        )
    else:
        sections.append("Очередь пока пуста.")
    sections.append(
        "<code>/ai_queue_retry UUID</code> — вернуть error/cancelled задачу\n"
        "<code>/ai_queue_cancel UUID причина</code> — отменить queued/running задачу"
    )
    await message.answer("\n\n".join(sections))


@router.message(Command("ai_queue_retry"))
async def handle_ai_queue_retry(
    message: Message,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    task_id = _parse_task_id(_arguments(message))
    if task_id is None:
        await message.answer("Использование: <code>/ai_queue_retry UUID</code>")
        return
    task = await ai_task_queue_service.requeue(task_id=task_id)
    if task is None:
        await message.answer(
            "Задача не найдена либо её статус не позволяет повторный запуск. "
            "Повторно ставятся только <code>error</code> и <code>cancelled</code>."
        )
        return
    await message.answer(
        f"<b>🔁 Задача возвращена в очередь.</b>\n"
        f"ID: <code>{task.id}</code>\n"
        f"Тип: <code>{escape(task.task_type)}</code>"
    )


@router.message(Command("ai_queue_cancel"))
async def handle_ai_queue_cancel(
    message: Message,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    arguments = _arguments(message)
    raw_id, separator, reason = arguments.partition(" ")
    task_id = _parse_task_id(raw_id)
    if task_id is None:
        await message.answer(
            "Использование: <code>/ai_queue_cancel UUID причина</code>"
        )
        return
    cancellation_reason = (
        reason.strip()
        if separator and reason.strip()
        else "Отменено владельцем через Telegram."
    )[:500]
    task = await ai_task_queue_service.cancel(
        task_id=task_id,
        reason=cancellation_reason,
    )
    if task is None:
        await message.answer(
            "Задача не найдена либо уже завершена. Отменить можно только "
            "<code>queued</code> или <code>running</code>."
        )
        return
    await message.answer(
        f"<b>🚫 AI-задача отменена.</b>\n"
        f"ID: <code>{task.id}</code>\n"
        f"Причина: <code>{escape(cancellation_reason)}</code>"
    )


@router.message(Command("ai_batch_plan"))
async def handle_ai_batch_plan(
    message: Message,
    database: Database,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    service = build_vision_batch_service(
        settings=load_settings(),
        database=database,
        usage_service=ai_usage_service,
        queue_service=ai_task_queue_service,
    )
    try:
        plan = await service.plan(
            limit=_batch_limit(message),
            created_by=_owner_id(message),
        )
        progress = await service.status(
            plan_id=plan.id,
            created_by=_owner_id(message),
        )
    except VisionBatchError as error:
        await message.answer(f"<b>VL-партия не создана.</b>\n{escape(str(error))}")
        return
    assert progress is not None
    text = _batch_text(progress)
    if plan.candidate_count:
        text += (
            "\n\nДля запуска подтвердите отдельно:\n"
            f"<code>/ai_batch_start {plan.id}</code>"
        )
    else:
        text += "\n\nНовых изображений для смыслового анализа не найдено."
    await message.answer(text)


@router.message(Command("ai_batch_start"))
async def handle_ai_batch_start(
    message: Message,
    database: Database,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    plan_id = _parse_task_id(_arguments(message))
    if plan_id is None:
        await message.answer("Использование: <code>/ai_batch_start UUID</code>")
        return
    service = build_vision_batch_service(
        settings=load_settings(),
        database=database,
        usage_service=ai_usage_service,
        queue_service=ai_task_queue_service,
    )
    try:
        await service.start(plan_id=plan_id, created_by=_owner_id(message))
        progress = await service.status(
            plan_id=plan_id,
            created_by=_owner_id(message),
        )
    except VisionBatchError as error:
        await message.answer(f"<b>VL-партия не запущена.</b>\n{escape(str(error))}")
        return
    assert progress is not None
    await message.answer(_batch_text(progress))


@router.message(Command("ai_batch_status"))
async def handle_ai_batch_status(
    message: Message,
    database: Database,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    raw = _arguments(message)
    plan_id = _parse_task_id(raw) if raw else None
    if raw and plan_id is None:
        await message.answer("Использование: <code>/ai_batch_status [UUID]</code>")
        return
    service = build_vision_batch_service(
        settings=load_settings(),
        database=database,
        usage_service=ai_usage_service,
        queue_service=ai_task_queue_service,
    )
    progress = await service.status(
        plan_id=plan_id,
        created_by=_owner_id(message),
    )
    if progress is None:
        await message.answer("Планы VL-партий пока не найдены.")
        return
    await message.answer(_batch_text(progress))


@router.message(Command("ai_batch_cancel"))
async def handle_ai_batch_cancel(
    message: Message,
    database: Database,
    ai_usage_service: AIUsageService,
    ai_task_queue_service: AITaskQueueService,
) -> None:
    arguments = _arguments(message)
    raw_id, separator, reason = arguments.partition(" ")
    plan_id = _parse_task_id(raw_id)
    if plan_id is None:
        await message.answer(
            "Использование: <code>/ai_batch_cancel UUID [причина]</code>"
        )
        return
    service = build_vision_batch_service(
        settings=load_settings(),
        database=database,
        usage_service=ai_usage_service,
        queue_service=ai_task_queue_service,
    )
    cancellation_reason = (
        reason.strip()
        if separator and reason.strip()
        else "VL-партия отменена владельцем."
    )
    plan = await service.cancel(plan_id=plan_id, reason=cancellation_reason)
    if plan is None:
        await message.answer("План не найден либо уже окончательно завершён.")
        return
    progress = await service.status(
        plan_id=plan.id,
        created_by=_owner_id(message),
    )
    assert progress is not None
    await message.answer(_batch_text(progress))


__all__ = (
    "_batch_text",
    "_snapshot_text",
    "_task_text",
    "handle_ai_batch_cancel",
    "handle_ai_batch_plan",
    "handle_ai_batch_start",
    "handle_ai_batch_status",
    "handle_ai_queue",
    "handle_ai_queue_cancel",
    "handle_ai_queue_retry",
    "router",
)
