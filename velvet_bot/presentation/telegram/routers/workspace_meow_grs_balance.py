from __future__ import annotations

import asyncio
from decimal import Decimal, ROUND_HALF_UP
from html import escape

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.infrastructure.ai import KieClient, KieError
from velvet_bot.presentation.telegram.routers.workspace_meow import MeowCallback
from velvet_bot.workspace_ui import workspace_callback

_GRS_BALANCE_TIMEOUT_SECONDS = 8
_USD_QUANTUM = Decimal("0.01")
_RUB_QUANTUM = Decimal("0.01")
_BYN_QUANTUM = Decimal("0.01")


def build_grs_balance_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Обновить баланс GRS",
                    callback_data=MeowCallback(
                        action="grs_balance",
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


async def handle_meow_grs_balance(
    callback: CallbackQuery,
    callback_data: MeowCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
) -> None:
    if not access_policy.allows_user(callback.from_user):
        await callback.answer("Баланс GRS доступен только владельцу.", show_alert=True)
        return
    await state.clear()
    if not kie_settings.enabled:
        await callback.answer("AI-генерация выключена на сервере.", show_alert=True)
        return
    if kie_settings.api_key is None or kie_settings.grs_api_key is None:
        await callback.answer("GRS AI не настроен на сервере.", show_alert=True)
        return

    credits: Decimal | None = None
    balance_error: str | None = None
    try:
        client = KieClient(
            api_key=kie_settings.api_key,
            models=kie_settings.models,
            base_url=kie_settings.base_url,
            file_upload_base_url=kie_settings.file_upload_base_url,
            grs_api_key=kie_settings.grs_api_key,
            grs_base_url=kie_settings.grs_base_url,
            timeout_seconds=min(kie_settings.timeout_seconds, _GRS_BALANCE_TIMEOUT_SECONDS),
            poll_interval_seconds=kie_settings.poll_interval_seconds,
            task_timeout_seconds=kie_settings.task_timeout_seconds,
        )
        credits = await asyncio.wait_for(
            client.get_grs_credits(),
            timeout=_GRS_BALANCE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        balance_error = "GRS AI не ответил за 8 секунд."
    except KieError as error:
        balance_error = str(error)

    text = _render_grs_balance(
        credits=credits,
        balance_error=balance_error,
        credit_usd=kie_settings.credit_usd,
        credit_byn=kie_settings.credit_byn,
        usd_to_rub=kie_settings.usd_to_rub,
    )
    keyboard = build_grs_balance_keyboard(workspace_id=callback_data.workspace_id)
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


def _render_grs_balance(
    *,
    credits: Decimal | None,
    balance_error: str | None,
    credit_usd: Decimal,
    credit_byn: Decimal,
    usd_to_rub: Decimal,
) -> str:
    lines = ["<b>Мяу · баланс GRS AI</b>", ""]
    if credits is None:
        lines.append("Баланс аккаунта: <b>не получен</b>")
    else:
        lines.extend(
            [
                f"Баланс аккаунта: <b>{_format_credits(credits)} кредитов</b>",
                "Стоимость остатка: "
                f"<b>{_format_money(credits, credit_usd=credit_usd, credit_byn=credit_byn, usd_to_rub=usd_to_rub)}</b>",
            ]
        )
    if balance_error:
        lines.extend(["", f"<i>Баланс временно недоступен: {escape(balance_error)}</i>"])
    lines.extend(
        [
            "",
            "<b>Расчётная стоимость одной генерации</b>",
            "• Nano Banana 2: <b>≈ 1 200 кредитов</b> · "
            + _format_money(
                Decimal("1200"),
                credit_usd=credit_usd,
                credit_byn=credit_byn,
                usd_to_rub=usd_to_rub,
            ),
            "• Nano Banana Pro: <b>≈ 1 800 кредитов</b> · "
            + _format_money(
                Decimal("1800"),
                credit_usd=credit_usd,
                credit_byn=credit_byn,
                usd_to_rub=usd_to_rub,
            ),
            "",
            "Баланс запрашивается только при открытии или обновлении этого экрана. Перед генерацией бот его больше не проверяет.",
        ]
    )
    return "\n".join(lines)


def _format_credits(value: Decimal) -> str:
    return f"{int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)):,}".replace(",", " ")


def _format_money(
    credits: Decimal,
    *,
    credit_usd: Decimal,
    credit_byn: Decimal,
    usd_to_rub: Decimal,
) -> str:
    usd = (credits * credit_usd).quantize(_USD_QUANTUM, rounding=ROUND_HALF_UP)
    rub = (usd * usd_to_rub).quantize(_RUB_QUANTUM, rounding=ROUND_HALF_UP)
    byn = (credits * credit_byn).quantize(_BYN_QUANTUM, rounding=ROUND_HALF_UP)
    return f"{usd} $ · {rub} ₽ · {byn} BYN"


__all__ = (
    "build_grs_balance_keyboard",
    "handle_meow_grs_balance",
)
