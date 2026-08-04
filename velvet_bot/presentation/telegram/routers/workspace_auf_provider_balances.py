from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
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
_CODEX_LIMITS_DEFAULT_BASE_URL = "http://hermes-coder-router:8878"


@dataclass(frozen=True, slots=True)
class ProviderBalance:
    value: Decimal | None
    unit: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class CodexLimitWindow:
    used_percent: Decimal
    window_duration_mins: int
    resets_at: int | None


@dataclass(frozen=True, slots=True)
class CodexSubscriptionLimits:
    plan_type: str
    windows: tuple[CodexLimitWindow, ...]
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
    balance_key = os.getenv("BYESU_BALANCE_API_KEY", "").strip()
    if balance_key:
        return balance_key

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
    except urllib.error.HTTPError as error:
        if error.code == 401:
            message = "ключ Byesu отклонён"
        elif error.code == 403:
            message = "доступ к квоте Byesu запрещён"
        elif error.code == 429:
            message = "Byesu временно ограничил запросы"
        else:
            message = f"Byesu вернул HTTP {error.code}"
        raise RuntimeError(message) from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError("сеть Byesu недоступна") from error
    except json.JSONDecodeError as error:
        raise RuntimeError("Byesu вернул неизвестный формат квоты") from error

    if not isinstance(payload, Mapping):
        raise RuntimeError("Byesu вернул неизвестный формат квоты")
    if payload.get("error"):
        raise RuntimeError("Byesu отклонил запрос квоты")
    return payload


async def _fetch_byesu_balance() -> ProviderBalance:
    api_key = _byesu_api_key()
    if not api_key:
        return ProviderBalance(None, "$", "API-ключ не настроен")
    try:
        subscription, usage = await asyncio.wait_for(
            asyncio.gather(
                asyncio.to_thread(_read_json, _BYESU_BILLING_URL, api_key=api_key, timeout_seconds=_PROVIDER_TIMEOUT_SECONDS),
                asyncio.to_thread(_read_json, _BYESU_BILLING_URL.replace("subscription", "usage"), api_key=api_key, timeout_seconds=_PROVIDER_TIMEOUT_SECONDS),
            ),
            timeout=_PROVIDER_TIMEOUT_SECONDS + 1,
        )
    except TimeoutError:
        return ProviderBalance(None, "$", "запрос квоты превысил время ожидания")
    except RuntimeError as error:
        return ProviderBalance(None, "$", str(error))

    limit = _decimal(subscription.get("hard_limit_usd"))
    used = _decimal(usage.get("total_usage"))
    if limit is None or used is None:
        return ProviderBalance(None, "$", "провайдер не вернул лимит или использование квоты")
    remaining = limit - used / Decimal("100")
    if remaining < 0:
        remaining = Decimal("0")
    return ProviderBalance(remaining.quantize(Decimal("0.01")), "$")


def _read_codex_limits_json(
    *,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
) -> Mapping[str, object]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/coders/velvet/rate-limits",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "VelvetBot/1.0 codex-limits",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code in {401, 403}:
            message = "доступ к лимитам Codex запрещён"
        else:
            message = f"Codex router вернул HTTP {error.code}"
        raise RuntimeError(message) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError("Codex router недоступен") from error
    except json.JSONDecodeError as error:
        raise RuntimeError("Codex вернул неизвестный формат лимитов") from error
    if not isinstance(payload, Mapping):
        raise RuntimeError("Codex вернул неизвестный формат лимитов")
    return payload


def _codex_window(value: object) -> CodexLimitWindow | None:
    if not isinstance(value, Mapping):
        return None
    used = _decimal(value.get("used_percent"))
    duration = value.get("window_duration_mins")
    reset = value.get("resets_at")
    if used is None or used > 100 or isinstance(duration, bool) or not isinstance(duration, int):
        return None
    if duration <= 0 or duration > 525_600:
        return None
    resets_at = reset if isinstance(reset, int) and not isinstance(reset, bool) and reset > 0 else None
    return CodexLimitWindow(used, duration, resets_at)


async def _fetch_codex_subscription_limits() -> CodexSubscriptionLimits:
    api_key = os.getenv("CODEX_LIMITS_API_KEY", "").strip()
    base_url = os.getenv(
        "CODEX_LIMITS_BASE_URL",
        _CODEX_LIMITS_DEFAULT_BASE_URL,
    ).strip()
    if not api_key or not base_url:
        return CodexSubscriptionLimits("unknown", (), "интеграция не настроена")
    try:
        payload = await asyncio.wait_for(
            asyncio.to_thread(
                _read_codex_limits_json,
                base_url=base_url,
                api_key=api_key,
                timeout_seconds=_PROVIDER_TIMEOUT_SECONDS,
            ),
            timeout=_PROVIDER_TIMEOUT_SECONDS + 1,
        )
    except TimeoutError:
        return CodexSubscriptionLimits("unknown", (), "запрос лимитов превысил время ожидания")
    except RuntimeError as error:
        return CodexSubscriptionLimits("unknown", (), str(error))
    plan_type = str(payload.get("plan_type") or "unknown").strip().casefold()
    windows = tuple(
        window
        for window in (
            _codex_window(payload.get("primary")),
            _codex_window(payload.get("secondary")),
        )
        if window is not None
    )
    if not windows:
        return CodexSubscriptionLimits(plan_type, (), "окна лимитов не возвращены")
    return CodexSubscriptionLimits(
        plan_type,
        tuple(sorted(windows, key=lambda item: item.window_duration_mins)),
    )


def _codex_plan_label(plan_type: str) -> str:
    return {
        "plus": "Plus",
        "pro": "Pro",
        "team": "Team",
        "business": "Business",
        "enterprise": "Enterprise",
    }.get(plan_type, "ChatGPT")


def _codex_window_label(minutes: int) -> str:
    if minutes % 10_080 == 0:
        days = minutes // 1_440
        return f"{days} дн."
    if minutes % 60 == 0:
        return f"{minutes // 60} ч"
    return f"{minutes} мин"


def _codex_reset_label(
    resets_at: int | None,
    *,
    now: datetime | None = None,
) -> str | None:
    if resets_at is None:
        return None
    current = now or datetime.now(timezone.utc)
    seconds = max(0, int(datetime.fromtimestamp(resets_at, timezone.utc).timestamp() - current.timestamp()))
    minutes = (seconds + 59) // 60
    days, minute_remainder = divmod(minutes, 1_440)
    hours, minute_remainder = divmod(minute_remainder, 60)
    if days:
        return f"сброс через {days} д {hours} ч"
    if hours:
        return f"сброс через {hours} ч {minute_remainder} мин"
    return f"сброс через {minute_remainder} мин"


def _codex_lines(
    limits: CodexSubscriptionLimits,
    *,
    now: datetime | None = None,
) -> list[str]:
    plan = _codex_plan_label(limits.plan_type)
    if limits.error:
        return [f"• <b>Codex {escape(plan)}</b>: {escape(limits.error)}"]
    result: list[str] = []
    for window in limits.windows:
        remaining = max(Decimal("0"), Decimal("100") - window.used_percent)
        reset = _codex_reset_label(window.resets_at, now=now)
        suffix = f" · {escape(reset)}" if reset else ""
        result.append(
            f"• <b>Codex {escape(plan)} · {_codex_window_label(window.window_duration_mins)}</b>: "
            f"<b>{_format_decimal(remaining)}% осталось</b>{suffix}"
        )
    return result



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
    (kie_balance, grs_balance), byesu_balance, codex_limits = await asyncio.gather(
        _fetch_kie_balances(kie_settings),
        _fetch_byesu_balance(),
        _fetch_codex_subscription_limits(),
    )
    wallet = wallet_overview.wallet
    text = "\n".join(
        [
            "<b>Служебные балансы · только Стэл</b>",
            "",
            "<b>Внешние провайдеры</b>",
            _provider_line("Kie.ai", kie_balance),
            _provider_line("GRS AI", grs_balance),
            _provider_line("Byesu · остаток квоты ключа", byesu_balance),
            *_codex_lines(codex_limits),
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
