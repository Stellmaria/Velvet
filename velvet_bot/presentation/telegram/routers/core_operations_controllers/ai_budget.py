from __future__ import annotations

from decimal import Decimal
from html import escape

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from velvet_bot.domains.ai_usage import AIBudgetStatus, AIUsageEvent, AIUsageService

router = Router(name=__name__)
_MAX_USAGE_EVENTS = 20


def _format_rub(value: Decimal) -> str:
    rendered = f"{value.quantize(Decimal('0.01')):,.2f}"
    return rendered.replace(",", " ").replace(".", ",") + " ₽"


def _command_argument(message: Message) -> str:
    text = (message.text or "").strip()
    _, separator, tail = text.partition(" ")
    return tail.strip() if separator else ""


def _usage_limit(message: Message) -> int:
    argument = _command_argument(message)
    if not argument:
        return 10
    try:
        value = int(argument)
    except ValueError:
        return 10
    return max(1, min(value, _MAX_USAGE_EVENTS))


def _budget_status_text(status: AIBudgetStatus) -> str:
    guard = "включён" if status.enabled else "выключен"
    runtime = "приостановлен" if status.paused else "работает"
    lines = [
        "<b>💳 AI-бюджет Velvet</b>",
        "",
        f"Guard: <b>{guard}</b>",
        f"Контур: <b>{runtime}</b>",
    ]
    if status.paused and status.pause_reason:
        lines.append(f"Причина: <code>{escape(status.pause_reason)}</code>")
    lines.extend(
        [
            "",
            "<b>Сегодня</b>",
            f"Фактически: <b>{_format_rub(status.today_rub)}</b> / {_format_rub(status.daily_limit_rub)}",
            f"Зарезервировано: {_format_rub(status.reserved_today_rub)}",
            f"Остаток: <b>{_format_rub(status.daily_remaining_rub)}</b>",
            "",
            "<b>Текущий месяц</b>",
            f"Фактически: <b>{_format_rub(status.month_rub)}</b> / {_format_rub(status.monthly_limit_rub)}",
            f"Зарезервировано: {_format_rub(status.reserved_month_rub)}",
            f"Остаток обычных AI-задач: <b>{_format_rub(status.ordinary_month_remaining_rub)}</b>",
            f"Полный остаток с резервом Hermes: {_format_rub(status.total_month_remaining_rub)}",
            "",
            f"Резерв Hermes: {_format_rub(status.hermes_reserve_rub)}",
            f"Лимит одного запроса: {_format_rub(status.max_request_rub)}",
        ]
    )
    if status.warning_month is not None and status.warning_percent is not None:
        lines.extend(
            [
                "",
                f"Последнее предупреждение: <b>{status.warning_percent}%</b> "
                f"за {status.warning_month:%m.%Y}",
            ]
        )
    lines.extend(
        [
            "",
            "<code>/ai_usage</code> — последние операции",
            "<code>/ai_pause причина</code> — остановить платные запросы",
            "<code>/ai_resume</code> — возобновить запросы",
        ]
    )
    return "\n".join(lines)


def _event_icon(status: str) -> str:
    return {
        "reserved": "⏳",
        "success": "✅",
        "error": "❌",
        "cancelled": "🚫",
    }.get(status, "•")


def _short(value: str, *, limit: int) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1] + "…"


def _event_text(event: AIUsageEvent) -> str:
    cost = (
        event.estimated_cost_rub
        if event.status == "reserved"
        else event.actual_cost_rub
    )
    tokens = event.input_tokens + event.output_tokens
    time_text = event.created_at.strftime("%d.%m %H:%M")
    latency = f" · {event.latency_ms} мс" if event.latency_ms is not None else ""
    return (
        f"{_event_icon(event.status)} <b>{escape(event.scope.value)}</b> · "
        f"<code>{escape(_short(event.model, limit=36))}</code>\n"
        f"   {escape(_short(event.operation, limit=42))} · {_format_rub(cost)} · "
        f"{tokens} ток. · {time_text}{latency}"
    )


@router.message(Command("ai_budget"))
async def handle_ai_budget(
    message: Message,
    ai_usage_service: AIUsageService,
) -> None:
    status = await ai_usage_service.status()
    await message.answer(_budget_status_text(status))


@router.message(Command("ai_usage"))
async def handle_ai_usage(
    message: Message,
    ai_usage_service: AIUsageService,
) -> None:
    limit = _usage_limit(message)
    events = await ai_usage_service.recent_events(limit=limit)
    if not events:
        await message.answer(
            "<b>AI-операции</b>\n\nЖурнал пока пуст. Платные запросы ещё не выполнялись."
        )
        return
    lines = [f"<b>Последние AI-операции: {len(events)}</b>", ""]
    lines.extend(_event_text(event) for event in events)
    await message.answer("\n\n".join(lines))


@router.message(Command("ai_pause"))
async def handle_ai_pause(
    message: Message,
    ai_usage_service: AIUsageService,
) -> None:
    reason = _command_argument(message) or "Приостановлено владельцем через Telegram."
    reason = reason[:500]
    user_id = message.from_user.id if message.from_user is not None else None
    await ai_usage_service.pause(reason=reason, updated_by=user_id)
    await message.answer(
        "<b>⏸ AI-контур приостановлен.</b>\n\n"
        "Новые РП, VL, Hermes и Codex-запросы через budget executor будут отклоняться.\n"
        f"Причина: <code>{escape(reason)}</code>"
    )


@router.message(Command("ai_resume"))
async def handle_ai_resume(
    message: Message,
    ai_usage_service: AIUsageService,
) -> None:
    user_id = message.from_user.id if message.from_user is not None else None
    await ai_usage_service.resume(updated_by=user_id)
    await message.answer(
        "<b>▶️ AI-контур возобновлён.</b> Новые запросы снова проходят budget guard."
    )


__all__ = (
    "_budget_status_text",
    "_event_text",
    "handle_ai_budget",
    "handle_ai_pause",
    "handle_ai_resume",
    "handle_ai_usage",
    "router",
)
