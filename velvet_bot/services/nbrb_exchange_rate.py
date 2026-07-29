from __future__ import annotations

import asyncio
import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from velvet_bot.database import Database

logger = logging.getLogger(__name__)


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
        return _parse_rates(payload)

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

    async def current_usd_to_rub(self, *, fallback: Decimal) -> Decimal:
        stored = await self.latest_success()
        if stored is not None and stored.usd_to_rub > 0:
            return stored.usd_to_rub
        return fallback


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
            logger.warning("Daily NBRB exchange-rate refresh failed: %s", error)
            return 0
        self._apply_rate(snapshot.usd_to_rub)
        logger.info(
            "NBRB exchange rate updated effective_date=%s usd_to_rub=%s",
            snapshot.effective_date,
            snapshot.usd_to_rub,
        )
        return 1

    def _apply_rate(self, value: Decimal) -> None:
        if self._on_rate is not None and value > 0:
            self._on_rate(value)


def _parse_rates(payload: Any) -> NbrbRateSnapshot:
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

    usd_date = _parse_date(usd.get("Date"))
    rub_date = _parse_date(rub.get("Date"))
    if usd_date != rub_date:
        raise NbrbRateError(
            f"NBRB вернул курсы за разные даты: USD={usd_date}, RUB={rub_date}."
        )

    usd_to_byn = _per_unit_rate(usd)
    rub_to_byn = _per_unit_rate(rub)
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


def _parse_date(value: object) -> date:
    text = str(value or "").strip()
    try:
        return date.fromisoformat(text.split("T", 1)[0])
    except ValueError as error:
        raise NbrbRateError(f"Некорректная дата курса NBRB: {text!r}.") from error


def _per_unit_rate(item: dict[str, Any]) -> Decimal:
    try:
        scale = Decimal(str(item.get("Cur_Scale")))
        official = Decimal(str(item.get("Cur_OfficialRate")))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise NbrbRateError("NBRB вернул некорректное числовое значение.") from error
    if scale <= 0:
        raise NbrbRateError("NBRB вернул неположительный масштаб валюты.")
    return official / scale


__all__ = (
    "DailyNbrbExchangeRateService",
    "NbrbExchangeRateRepository",
    "NbrbRateClient",
    "NbrbRateError",
    "NbrbRateSnapshot",
    "StoredExchangeRate",
)
