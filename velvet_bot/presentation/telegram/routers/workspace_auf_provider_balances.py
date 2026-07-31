from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Mapping

from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from velvet_bot.core.config.kie import KieSettings
from velvet_bot.domains.auf_runtime import AufRuntimeService
from velvet_bot.domains.auf_wallet import AufWalletService, format_auf_units
from velvet_bot.infrastructure.ai import KieClient, KieError
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback
from velvet_bot.workspace_ui import workspace_callback

_PROVIDER_TIMEOUT_SECONDS = 8
_BYESU_BILLING_URL = "https://byesu.com/dashboard/billing/subscription"


@dataclass(frozen=True, slots=True)
class ProviderBalance:
    value: Decimal | None
    unit: str
    error: str | None = None


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError):
        return None
    if not result.is_finite() or result < 0:
        return None
    return result


def _byesu_api_key() -> str | None:
    direct = os.getenv("BYESU_API_KEY", "").strip()
    if direct:
        return direct
    candidates = (
        ("AI_VISION_BASE_URL", "AI_VISION_API_KEY"),
        ("AI_TEXT_BASE_URL", "AI_TEXT_API_KEY"),
        ("AI_TEXT_FALLBACK_BASE_URL", "AI_TEXT_FALLBACK_API_KEY"),
    )
    for base_name, key_name in candidates:
        base_url = os.getenv(base_name, "").strip().casefold()
        api_key = os.getenv(key_name, "").strip()
        if "byesu.com" in base_url and api_key:
            return api_key
    return None


def _read_json(
    url: str,
    *,
    api_key: str,
    timeout_seconds: int,
) -> Mapping[str, object]:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "VelvetBot/1.0 provider-balance",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError("Byesu не ответил на запрос баланса.") from error
    if not isinstance(payload, Mapping):
        raise RuntimeError("Byesu вернул неизвестный формат баланса.")
    if payload.get("error"):
        raise RuntimeError("Byesu отклонил запрос баланса.")
    return payload


async def _fetch_byesu_balance() -> ProviderBalance:
    api_key = _byesu_api_key()
    if not api_key:
        return ProviderBalance(None, "$", "API-ключ не настроен")
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(
                _read_json,
                _BYESU_BILLING_URL,
                api_key=api_key,
                timeout_seconds=_PROVIDER_TIMEOUT_SECONDS,
            ),
            timeout=_PROVIDER_TIMEOUT_SECONDS + 1,
        )
    except (RuntimeError, TimeoutError):
        return ProviderBalance(None, "$", "баланс временно недоступен")

    value = _decimal(payload.get("balance_usd"))
    if value is None:
        return ProviderBalance(None, "$", "провайдер не вернул остаток баланса")
    return ProviderBalance(value, "$")


async def _fetch_kie_balances(
    kie_settings: KieSettings,
) -> tuple[ProviderBalance, ProviderBalance]:
    if not kie_settings.enabled or kie_settings.api_key is None:
        kie = ProviderBalance(None, "credits", "API-ключ не настроен")
    else:
        kie = ProviderBalance(None, "credits", "баланс временно недоступен")

    if kie_settings.grs_api_key is None:
        grs = ProviderBalance(None, "credits", "API-ключ не настроен")
    else:
        grs = ProviderBalance(None, "credits", "баланс временно недоступен")

    if kie_settings.api_key is None:
        return kie, grs

    client = KieClient(
        api_key=kie_settings.api_key,
        models=kie_settings.models,
        base_url=kie_settings.base_url,
        file_upload_base_url=kie_settings.file_upload_base_url,
        grs_api_key=kie_settings.grs_api_key,
        grs_base_url=kie_settings.grs_base_url,
        timeout_seconds=min(kie_settings.timeout_seconds, _PROVIDER_TIMEOUT_SECONDS),
        poll_interval_seconds=kie_settings.poll_interval_seconds,
        task_timeout_seconds=kie_settings.task_timeout_seconds,
    )

    async def fetch_kie() -> ProviderBalance:
        try:
            value = await asyncio.wait_for(
                client.get_account_credits(),
                timeout=_PROVIDER_TIMEOUT_SECONDS,
            )
        except (KieError, TimeoutError):
            return kie
        return ProviderBalance(value, "credits")

    async def fetch_grs() -> ProviderBalance:
        if kie_settings.grs_api_key is None:
            return grs
        try:
            value = await asyncio.wait_for(
                client.get_grs_credits(),
                timeout=_PROVIDER_TIMEOUT_SECONDS,
            )
        except (KieError, TimeoutError):
            return grs
        return ProviderBalance(value, "credits")

    kie_result, grs_result = await asyncio.gather(fetch_kie(), fetch_grs())
    return kie_result, grs_result


def _format_decimal(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.0001"))
    text = format(normalized, "f").rstrip("0").rstrip(".")
    return text or "0"


def _provider_line(name: str, balance: ProviderBalance) -> str:
    if balance.value is None:
        return f"• <b>{escape(name)}</b>: {escape(balance.error or 'недоступно')}"
    if balance.unit == "$":
        return f"• <b>{escape(name)}</b>: <b>${_format_decimal(balance.value)}</b>"
    return (
        f"• <b>{escape(name)}</b>: "
        f"<b>{_format_decimal(balance.value)} {escape(balance.unit)}</b>"
    )


def build_provider_balances_keyboard(*, workspace_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Обновить балансы",
                    callback_data=AufCallback(
                        action="provider_balances",
                        workspace_id=workspace_id,
                    ).pack(),
                )
            ],
            [
                InlineKeyboardButton(text="Kie.ai", url="https://kie.ai/"),
                InlineKeyboardButton(text="GRS AI", url="https://grsai.com/"),
            ],
            [
                InlineKeyboardButton(
                    text="Byesu",
                    url="https://byesu.com/media/query.html",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="↩️ Ауф",
                    callback_data=workspace_callback("auf", workspace_id=workspace_id),
                )
            ],
        ]
    )


async def handle_auf_provider_balances(
    callback: CallbackQuery,
    callback_data: AufCallback,
    state: FSMContext,
    kie_settings: KieSettings,
    auf_runtime_service: AufRuntimeService,
    auf_wallet_service: AufWalletService,
) -> None:
    user_id = callback.from_user.id
    if not auf_runtime_service.is_global_owner(user_id):
        await callback.answer("Балансы провайдеров доступны только Стэл.", show_alert=True)
        return

    try:
        await auf_runtime_service.require_workspace_access(
            workspace_id=callback_data.workspace_id,
            actor_user_id=user_id,
        )
        wallet_overview = await auf_wallet_service.overview(
            workspace_id=callback_data.workspace_id,
            actor_user_id=user_id,
            history_limit=1,
        )
    except (PermissionError, ValueError) as error:
        await callback.answer(str(error), show_alert=True)
        return

    await state.clear()
    (kie_balance, grs_balance), byesu_balance = await asyncio.gather(
        _fetch_kie_balances(kie_settings),
        _fetch_byesu_balance(),
    )
    wallet = wallet_overview.wallet
    text = "\n".join(
        [
            "<b>Служебные балансы · только Стэл</b>",
            "",
            "<b>Внешние провайдеры</b>",
            _provider_line("Kie.ai", kie_balance),
            _provider_line("GRS AI", grs_balance),
            _provider_line("Byesu", byesu_balance),
            "",
            "<b>Внутренний кошелёк Velvet</b>",
            f"• Доступно: <b>{format_auf_units(wallet.available_units)}</b>",
            f"• В резерве: <b>{format_auf_units(wallet.reserved_units)}</b>",
            f"• Потрачено за 30 дней: <b>{format_auf_units(wallet_overview.spent_30d_units)}</b>",
            "",
            "<i>Внешние значения обновляются прямыми запросами к API. "
            "Ключи и технические ответы в Telegram не выводятся.</i>",
        ]
    )
    keyboard = build_provider_balances_keyboard(workspace_id=callback_data.workspace_id)
    if isinstance(callback.message, Message):
        try:
            await callback.message.edit_text(text, reply_markup=keyboard)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).casefold():
                await callback.message.answer(text, reply_markup=keyboard)
    await callback.answer()


__all__ = (
    "ProviderBalance",
    "build_provider_balances_keyboard",
    "handle_auf_provider_balances",
)
