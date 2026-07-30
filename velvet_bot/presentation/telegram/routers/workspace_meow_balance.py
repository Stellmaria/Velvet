from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

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
    "grok_imagine_video_15": "Grok Imagine Video 1.5",
    "seedance_15_pro_video": "Seedance 1.5 Pro",
    "wan_26_image_to_video": "Wan 2.7",
}
_USD_QUANTUM = Decimal("0.0001")
_RUB_QUANTUM = Decimal("0.01")
_BYN_QUANTUM = Decimal("0.0001")


class NbrbRateError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class NbrbRateSnapshot:
    effective_date: date
    usd_to_byn: Decimal
    rub_to_byn: Decimal
    usd_to_rub: Decimal


@dataclass(frozen=True, slots=True)
class StoredExchangeRate:
    effective_date: date
    usd_to_byn: Decimal
    rub_to_byn: Decimal
    usd_to_rub: Decimal
    fetched_at: datetime


class NbrbRateClient:
    def __init__(
        self,
        *,
        base_url: str = "https://api.nbrb.by",
        timeout_seconds: int = 20,
        transport: Callable[[str, int], Any] | None = None,
    ) -> None:
        self.base_url = base_url.strip().rstrip("/")
        self.timeout_seconds = max(5, min(int(timeout_seconds), 120))
        self._transport = transport or self._read_json
        if not self.base_url:
            raise ValueError("NBRB base_url не может быть пустым.")

    async def fetch(self, *, on_date: date) -> NbrbRateSnapshot:
        query = urllib.parse.urlencode(
            {"ondate": on_date.isoformat(), "periodicity": "0"}
        )
        url = f"{self.base_url}/exrates/rates?{query}"
        payload = await asyncio.to_thread(
            self._transport,
            url,
            self.timeout_seconds,
        )
        return _parse_nbrb_rates(payload)

    @staticmethod
    def _read_json(url: str, timeout_seconds: int) -> Any:
        request = urllib.request.Request(
            url,
            headers={"Accept": "application/json", "User-Agent": "VelvetBot/1.0"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                raw = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise NbrbRateError(f"NBRB недоступен: {error}") from error
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise NbrbRateError("NBRB вернул некорректный JSON.") from error


class NbrbExchangeRateRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def claim_daily_attempt(self, check_date: date) -> bool:
        async with self._database.acquire() as connection:
            result = await connection.execute(
                """
                INSERT INTO kie_exchange_rate_daily (
                    check_date, source, attempted_at
                )
                VALUES ($1::DATE, 'nbrb', NOW())
                ON CONFLICT (check_date) DO NOTHING
                """,
                check_date,
            )
        return result.endswith("1")

    async def mark_success(
        self,
        *,
        check_date: date,
        snapshot: NbrbRateSnapshot,
    ) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE kie_exchange_rate_daily
                SET effective_date = $2::DATE,
                    usd_to_byn = $3::NUMERIC,
                    rub_to_byn = $4::NUMERIC,
                    usd_to_rub = $5::NUMERIC,
                    succeeded_at = NOW(),
                    error_message = NULL
                WHERE check_date = $1::DATE
                """,
                check_date,
                snapshot.effective_date,
                snapshot.usd_to_byn,
                snapshot.rub_to_byn,
                snapshot.usd_to_rub,
            )

    async def mark_error(self, *, check_date: date, error: BaseException) -> None:
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                UPDATE kie_exchange_rate_daily
                SET error_message = $2::TEXT
                WHERE check_date = $1::DATE
                """,
                check_date,
                str(error)[:2000],
            )

    async def latest_success(self) -> StoredExchangeRate | None:
        async with self._database.acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT effective_date, usd_to_byn, rub_to_byn, usd_to_rub,
                       succeeded_at
                FROM kie_exchange_rate_daily
                WHERE succeeded_at IS NOT NULL
                ORDER BY effective_date DESC, succeeded_at DESC
                LIMIT 1
                """
            )
        if row is None:
            return None
        return StoredExchangeRate(
            effective_date=row["effective_date"],
            usd_to_byn=Decimal(row["usd_to_byn"]),
            rub_to_byn=Decimal(row["rub_to_byn"]),
            usd_to_rub=Decimal(row["usd_to_rub"]),
            fetched_at=row["succeeded_at"],
        )


class DailyNbrbExchangeRateService:
    def __init__(
        self,
        *,
        repository: NbrbExchangeRateRepository,
        client: NbrbRateClient,
        timezone_name: str = "Europe/Minsk",
        on_rate: Callable[[Decimal], None] | None = None,
    ) -> None:
        self._repository = repository
        self._client = client
        self._timezone = ZoneInfo(timezone_name)
        self._on_rate = on_rate
        self._restored = False

    async def process_once(self) -> int:
        if not self._restored:
            self._restored = True
            stored = await self._repository.latest_success()
            if stored is not None:
                self._apply_rate(stored.usd_to_rub)

        check_date = datetime.now(self._timezone).date()
        if not await self._repository.claim_daily_attempt(check_date):
            return 0
        try:
            snapshot = await self._client.fetch(on_date=check_date)
            await self._repository.mark_success(
                check_date=check_date,
                snapshot=snapshot,
            )
        except asyncio.CancelledError:
            raise
        except (NbrbRateError, ValueError, ArithmeticError, OSError) as error:
            await self._repository.mark_error(check_date=check_date, error=error)
            return 0
        self._apply_rate(snapshot.usd_to_rub)
        return 1

    def _apply_rate(self, value: Decimal) -> None:
        if self._on_rate is not None and value > 0:
            self._on_rate(value)


def _parse_nbrb_rates(payload: Any) -> NbrbRateSnapshot:
    if not isinstance(payload, list):
        raise NbrbRateError("NBRB вернул не список курсов.")
    entries = {
        str(item.get("Cur_Abbreviation") or "").upper(): item
        for item in payload
        if isinstance(item, dict)
    }
    usd = entries.get("USD")
    rub = entries.get("RUB")
    if usd is None or rub is None:
        raise NbrbRateError("В ответе NBRB отсутствует USD или RUB.")

    usd_date = _parse_nbrb_date(usd.get("Date"))
    rub_date = _parse_nbrb_date(rub.get("Date"))
    if usd_date != rub_date:
        raise NbrbRateError(
            f"NBRB вернул курсы за разные даты: USD={usd_date}, RUB={rub_date}."
        )

    usd_to_byn = _nbrb_per_unit_rate(usd)
    rub_to_byn = _nbrb_per_unit_rate(rub)
    if usd_to_byn <= 0 or rub_to_byn <= 0:
        raise NbrbRateError("NBRB вернул неположительный курс.")
    usd_to_rub = usd_to_byn / rub_to_byn
    if usd_to_rub <= 0:
        raise NbrbRateError("Не удалось вычислить положительный USD/RUB.")
    return NbrbRateSnapshot(
        effective_date=usd_date,
        usd_to_byn=usd_to_byn,
        rub_to_byn=rub_to_byn,
        usd_to_rub=usd_to_rub,
    )


def _parse_nbrb_date(value: object) -> date:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text.split("T", 1)[0])
    except ValueError as error:
        raise NbrbRateError(f"Некорректная дата курса NBRB: {text!r}.") from error


def _nbrb_per_unit_rate(item: dict[str, Any]) -> Decimal:
    try:
        scale = Decimal(str(item.get("Cur_Scale")))
        official = Decimal(str(item.get("Cur_OfficialRate")))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise NbrbRateError("NBRB вернул некорректное числовое значение.") from error
    if scale <= 0:
        raise NbrbRateError("NBRB вернул неположительный масштаб валюты.")
    return official / scale


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
    stored_rate = await NbrbExchangeRateRepository(database).latest_success()
    usd_to_rub = (
        stored_rate.usd_to_rub
        if stored_rate is not None and stored_rate.usd_to_rub > 0
        else kie_settings.usd_to_rub
    )
    text = _render_balance(
        live_credits=live_credits,
        balance_error=balance_error,
        summary=summary,
        recent=recent,
        credit_usd=kie_settings.credit_usd,
        credit_byn=kie_settings.credit_byn,
        usd_to_rub=usd_to_rub,
        concurrency=kie_settings.max_concurrent_generations,
        attempts=kie_settings.generation_max_attempts,
    )
    if stored_rate is not None:
        text += (
            "\nКурс USD/RUB: "
            f"<b>{_format_number(stored_rate.usd_to_rub, places=4, minimum_places=4)} ₽</b> "
            f"по НБРБ на <b>{stored_rate.effective_date:%d.%m.%Y}</b>."
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
                    {credits_sql} AS consumed_credits,
                    completed_at
                FROM ai_usage_events
                WHERE provider='kie' AND status='success'
                ORDER BY id DESC
                LIMIT 5"""
        )
    summary = {
        "consumed_credits": Decimal(usage["consumed_credits"] or 0) if usage else Decimal("0"),
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
    credit_usd: Decimal,
    credit_byn: Decimal,
    usd_to_rub: Decimal,
    concurrency: int,
    attempts: int,
) -> str:
    consumed_credits = _decimal(summary["consumed_credits"])
    if live_credits is None:
        live_lines = ["Баланс аккаунта: <b>не получен</b>"]
    else:
        live_lines = [
            f"Баланс аккаунта: <b>{_format_credits(live_credits)} кредитов</b>",
            "Стоимость остатка: "
            f"<b>{_format_credit_money(live_credits, credit_usd=credit_usd, credit_byn=credit_byn, usd_to_rub=usd_to_rub)}</b>",
        ]
    lines = [
        "<b>Мяу · баланс Kie</b>",
        "",
        *live_lines,
        f"Списано по сохранённым задачам: <b>{_format_credits(consumed_credits)} кредитов</b>",
        "Себестоимость списаний: "
        f"<b>{_format_credit_money(consumed_credits, credit_usd=credit_usd, credit_byn=credit_byn, usd_to_rub=usd_to_rub)}</b>",
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
            credits_value = _decimal(row.get("consumed_credits"))
            credits = _format_credits(credits_value)
            money = _format_credit_money(
                credits_value,
                credit_usd=credit_usd,
                credit_byn=credit_byn,
                usd_to_rub=usd_to_rub,
            )
            lines.append(f"• {escape(model)}: <b>{credits} кр.</b> · {money}")
    one_credit = _format_credit_money(
        Decimal("1"),
        credit_usd=credit_usd,
        credit_byn=credit_byn,
        usd_to_rub=usd_to_rub,
    )
    lines.extend(
        [
            "",
            f"Расчёт себестоимости: <b>1 кредит = {one_credit}</b>.",
            "Кредиты берутся из ответа Kie <code>creditsConsumed</code>; деньги теперь считаются от фактического числа кредитов, а не от приблизительного тарифа модели.",
        ]
    )
    return "\n".join(lines)


def _decimal(value: object) -> Decimal:
    try:
        return Decimal(value or 0)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _format_credits(value: Decimal) -> str:
    normalized = format(value.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _format_credit_money(
    credits: Decimal,
    *,
    credit_usd: Decimal,
    credit_byn: Decimal,
    usd_to_rub: Decimal,
) -> str:
    usd = (credits * credit_usd).quantize(_USD_QUANTUM, rounding=ROUND_HALF_UP)
    rub = (usd * usd_to_rub).quantize(_RUB_QUANTUM, rounding=ROUND_HALF_UP)
    byn = (credits * credit_byn).quantize(_BYN_QUANTUM, rounding=ROUND_HALF_UP)
    return " · ".join(
        (
            f"{_format_number(usd, places=4, minimum_places=2)} $",
            f"{_format_number(rub, places=2, minimum_places=2)} ₽",
            f"{_format_number(byn, places=4, minimum_places=2)} BYN",
        )
    )


def _format_number(value: Decimal, *, places: int, minimum_places: int) -> str:
    text = f"{value:,.{places}f}"
    integer, fraction = text.split(".", 1)
    fraction = fraction.rstrip("0")
    fraction += "0" * max(0, minimum_places - len(fraction))
    integer = integer.replace(",", "\u00a0")
    return f"{integer},{fraction}"


__all__ = (
    "DailyNbrbExchangeRateService",
    "NbrbExchangeRateRepository",
    "NbrbRateClient",
    "NbrbRateError",
    "NbrbRateSnapshot",
    "StoredExchangeRate",
    "build_kie_balance_keyboard",
    "handle_meow_balance",
)
