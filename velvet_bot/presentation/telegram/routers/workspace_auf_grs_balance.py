from __future__ import annotations

import asyncio
from decimal import Decimal, ROUND_HALF_UP

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.access import AccessPolicy
from velvet_bot.core.config.kie import KieSettings
from velvet_bot.infrastructure.ai import KieClient, KieError
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback
from velvet_bot.workspace_ui import workspace_callback

_GRS_BALANCE_TIMEOUT_SECONDS = 8
_NANO_BANANA_2_CREDITS = Decimal("1200")
_NANO_BANANA_PRO_CREDITS = Decimal("1800")
_USD_QUANTUM = Decimal("0.0001")
_RUB_QUANTUM = Decimal("0.01")


def build_grs_balance_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Обновить служебный статус",
                    callback_data=AufCallback(
                        action="grs_balance",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Ауф",
                    callback_data=workspace_callback("meow", workspace_id=workspace_id),
                )
            ],
        ]
    )


async def handle_auf_grs_balance(
    callback: CallbackQuery,
    callback_data: AufCallback,
    state: FSMContext,
    access_policy: AccessPolicy,
    kie_settings: KieSettings,
) -> None:
    if not access_policy.allows_user(callback.from_user):
        await callback.answer(
            "Служебный статус доступен только владельцу.",
            show_alert=True,
        )
        return
    await state.clear()
    if not kie_settings.enabled:
        await callback.answer("Генерация сейчас недоступна.", show_alert=True)
        return
    if kie_settings.api_key is None or kie_settings.grs_api_key is None:
        await callback.answer(
            "Этот служебный экран сейчас недоступен.",
            show_alert=True,
        )
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
            timeout_seconds=min(
                kie_settings.timeout_seconds,
                _GRS_BALANCE_TIMEOUT_SECONDS,
            ),
            poll_interval_seconds=kie_settings.poll_interval_seconds,
            task_timeout_seconds=kie_settings.task_timeout_seconds,
        )
        credits = await asyncio.wait_for(
            client.get_grs_credits(),
            timeout=_GRS_BALANCE_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        balance_error = "Служебный статус не ответил вовремя."
    except KieError:
        balance_error = "Служебный статус временно недоступен."

    text = _render_grs_balance(
        credits=credits,
        balance_error=balance_error,
        nano_banana_2_usd=kie_settings.pricing.nano_banana_2_usd,
        nano_banana_pro_usd=(
            kie_settings.pricing.nano_banana_pro_usd
            or kie_settings.pricing.nano_1k_2k_usd
        ),
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
    nano_banana_2_usd: Decimal,
    nano_banana_pro_usd: Decimal,
    usd_to_rub: Decimal,
) -> str:
    del nano_banana_2_usd, nano_banana_pro_usd, usd_to_rub
    lines = ["<b>Ауф · служебный статус генерации</b>", ""]
    lines.append(
        "Состояние: <b>доступно</b>"
        if credits is not None
        else "Состояние: <b>временно недоступно</b>"
    )
    if balance_error:
        lines.extend(["", f"<i>{balance_error}</i>"])
    lines.extend(
        [
            "",
            "Названия внешних сервисов, их баланс, тарифы и технические "
            "идентификаторы в пользовательском интерфейсе не показываются.",
        ]
    )
    return "\n".join(lines)


def _grs_credit_usd(
    *,
    nano_banana_2_usd: Decimal,
    nano_banana_pro_usd: Decimal,
) -> Decimal:
    rates = []
    if nano_banana_2_usd > 0:
        rates.append(nano_banana_2_usd / _NANO_BANANA_2_CREDITS)
    if nano_banana_pro_usd > 0:
        rates.append(nano_banana_pro_usd / _NANO_BANANA_PRO_CREDITS)
    if not rates:
        return Decimal("0")
    return sum(rates, Decimal("0")) / Decimal(len(rates))


def _format_credits(value: Decimal) -> str:
    return f"{int(value.quantize(Decimal('1'), rounding=ROUND_HALF_UP)):,}".replace(
        ",",
        " ",
    )


def _format_usd_rub(usd: Decimal, *, usd_to_rub: Decimal) -> str:
    normalized_usd = usd.quantize(_USD_QUANTUM, rounding=ROUND_HALF_UP)
    rub = (usd * usd_to_rub).quantize(_RUB_QUANTUM, rounding=ROUND_HALF_UP)
    return f"{normalized_usd} $ · {rub} ₽"


__all__ = (
    "build_grs_balance_keyboard",
    "handle_auf_grs_balance",
)
