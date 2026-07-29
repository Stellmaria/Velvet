from __future__ import annotations

from decimal import Decimal
from html import escape
from typing import Any

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.database import Database
from velvet_bot.infrastructure.ai import KieClient, KieError
from velvet_bot.presentation.telegram.routers.workspace_meow import MeowCallback
from velvet_bot.workspace_ui import workspace_callback

_MODEL_NAMES = {
    "seedream_5_pro": "Seedream 5 Pro",
    "nano_banana_pro": "Nano Banana Pro",
    "grok_imagine_video": "Grok Imagine v1",
    "seedance_15_pro_video": "Seedance 1.5 Pro",
    "wan_26_image_to_video": "Wan 2.6",
}


def build_kie_balance_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Обновить баланс",
                    callback_data=MeowCallback(
                        action="balance",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Мяу",
                    callback_data=workspace_callback("meow", workspace_id=workspace_id),
                )
            ],
        ]
    )


async def handle_meow_balance(
    callback: CallbackQuery,
    callback_data: MeowCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
    database: Database,
) -> None:
    if not access_policy.allows_user(callback.from_user):
        await callback.answer("Баланс Kie доступен только владельцу.", show_alert=True)
        return
    await state.clear()
    if not kie_settings.enabled or kie_settings.api_key is None:
        await callback.answer("Kie.ai выключен на сервере.", show_alert=True)
        return

    live_credits: Decimal | None = None
    balance_error: str | None = None
    try:
        client = KieClient(
            api_key=kie_settings.api_key,
            models=kie_settings.models,
            base_url=kie_settings.base_url,
            file_upload_base_url=kie_settings.file_upload_base_url,
            timeout_seconds=kie_settings.timeout_seconds,
            poll_interval_seconds=kie_settings.poll_interval_seconds,
            task_timeout_seconds=kie_settings.task_timeout_seconds,
        )
        live_credits = await client.get_account_credits()
    except KieError as error:
        balance_error = str(error)

    summary, recent = await _load_kie_usage(database)
    text = _render_balance(
        live_credits=live_credits,
        balance_error=balance_error,
        summary=summary,
        recent=recent,
        concurrency=kie_settings.max_concurrent_generations,
        attempts=kie_settings.generation_max_attempts,
    )
    keyboard = build_kie_balance_keyboard(workspace_id=callback_data.workspace_id)
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


async def _load_kie_usage(
    database: Database,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    credits_sql = """CASE
        WHEN COALESCE(metadata->>'consumed_credits','') ~ '^[0-9]+([.][0-9]+)?$'
        THEN (metadata->>'consumed_credits')::NUMERIC
        ELSE 0::NUMERIC
    END"""
    async with database.acquire() as connection:
        usage = await connection.fetchrow(
            f"""SELECT
                    COALESCE(SUM({credits_sql}) FILTER (WHERE status='success'),0) AS consumed_credits,
                    COALESCE(SUM(actual_cost_rub) FILTER (WHERE status='success'),0) AS actual_cost_rub,
                    COUNT(*) FILTER (WHERE status='success') AS success_count,
                    COUNT(*) FILTER (WHERE status='error') AS error_count,
                    COUNT(*) FILTER (WHERE status='reserved') AS reserved_count
                FROM ai_usage_events
                WHERE provider='kie'"""
        )
        queue = await connection.fetchrow(
            """SELECT
                    COUNT(*) FILTER (WHERE status='queued') AS queued,
                    COUNT(*) FILTER (WHERE status='running') AS running
                FROM ai_tasks
                WHERE task_type='media.generate.kie'"""
        )
        rows = await connection.fetch(
            f"""SELECT
                    COALESCE(metadata->>'model_alias',model) AS model_name,
                    actual_cost_rub,
                    {credits_sql} AS consumed_credits,
                    completed_at
                FROM ai_usage_events
                WHERE provider='kie' AND status='success'
                ORDER BY id DESC
                LIMIT 5"""
        )
    summary = {
        "consumed_credits": Decimal(usage["consumed_credits"] or 0) if usage else Decimal("0"),
        "actual_cost_rub": Decimal(usage["actual_cost_rub"] or 0) if usage else Decimal("0"),
        "success_count": int(usage["success_count"] or 0) if usage else 0,
        "error_count": int(usage["error_count"] or 0) if usage else 0,
        "reserved_count": int(usage["reserved_count"] or 0) if usage else 0,
        "queued": int(queue["queued"] or 0) if queue else 0,
        "running": int(queue["running"] or 0) if queue else 0,
    }
    return summary, tuple(dict(row) for row in rows)


def _render_balance(
    *,
    live_credits: Decimal | None,
    balance_error: str | None,
    summary: dict[str, object],
    recent: tuple[dict[str, object], ...],
    concurrency: int,
    attempts: int,
) -> str:
    if live_credits is None:
        live_line = "Баланс аккаунта: <b>не получен</b>"
    else:
        live_line = f"Баланс аккаунта: <b>{_format_credits(live_credits)} кредитов</b>"
    lines = [
        "<b>Мяу · баланс Kie</b>",
        "",
        live_line,
        f"Списано по сохранённым задачам: <b>{_format_credits(_decimal(summary['consumed_credits']))} кредитов</b>",
        f"Учтённая себестоимость: <b>{_format_rub(_decimal(summary['actual_cost_rub']))}</b>",
        "",
        f"Активно: <b>{int(summary['running'])}/{concurrency}</b>",
        f"В очереди: <b>{int(summary['queued'])}</b>",
        f"Зарезервировано бюджетом: <b>{int(summary['reserved_count'])}</b>",
        f"Попыток на задачу: <b>{attempts}</b>",
        "",
        f"Успешно: <b>{int(summary['success_count'])}</b> · ошибок: <b>{int(summary['error_count'])}</b>",
    ]
    if balance_error:
        lines.extend(["", f"<i>Live-баланс временно недоступен: {escape(balance_error)}</i>"])
    lines.extend(["", "<b>Последние списания Kie</b>"])
    if not recent:
        lines.append("Пока нет завершённых задач с учётом кредитов.")
    else:
        for row in recent:
            alias = str(row.get("model_name") or "kie")
            model = _MODEL_NAMES.get(alias, alias)
            credits = _format_credits(_decimal(row.get("consumed_credits")))
            rub = _format_rub(_decimal(row.get("actual_cost_rub")))
            lines.append(f"• {escape(model)}: <b>{credits} кр.</b> · {rub}")
    lines.extend(
        [
            "",
            "Кредиты берутся из ответа Kie <code>creditsConsumed</code>. Рубли — локальная себестоимость по настроенным тарифам.",
        ]
    )
    return "\n".join(lines)


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(value or 0)
    except (TypeError, ValueError):
        return Decimal("0")


def _format_credits(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _format_rub(value: Decimal) -> str:
    normalized = f"{value:,.2f}".replace(",", "\u00a0").replace(".", ",")
    return f"{normalized} ₽"


__all__ = (
    "build_kie_balance_keyboard",
    "handle_meow_balance",
)
