from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from enum import StrEnum
from typing import Mapping
from uuid import UUID

AUF_SCALE = 10_000
_AUF_QUANT = Decimal("0.0001")


class AufWalletStatus(StrEnum):
    ACTIVE = "active"
    FROZEN = "frozen"


class AufWalletOperation(StrEnum):
    GRANT = "grant"
    PURCHASE = "purchase"
    RESERVE = "reserve"
    RELEASE = "release"
    CAPTURE = "capture"
    REFUND = "refund"
    MANUAL_DEBIT = "manual_debit"
    ADJUSTMENT = "adjustment"


@dataclass(frozen=True, slots=True)
class AufEconomySettings:
    provider_auf_usd: Decimal
    retail_auf_usd: Decimal
    billing_usd_to_rub: Decimal
    billing_usd_to_byn: Decimal
    retail_markup_percent: Decimal
    updated_by_user_id: int | None
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class AufWallet:
    workspace_id: int
    available_units: int
    reserved_units: int
    status: AufWalletStatus
    created_at: datetime
    updated_at: datetime

    @property
    def total_units(self) -> int:
        return self.available_units + self.reserved_units

    @property
    def available_auf(self) -> Decimal:
        return units_to_auf(self.available_units)

    @property
    def reserved_auf(self) -> Decimal:
        return units_to_auf(self.reserved_units)


@dataclass(frozen=True, slots=True)
class AufWalletEntry:
    id: int
    workspace_id: int
    operation_type: AufWalletOperation
    amount_units: int
    available_after_units: int
    reserved_after_units: int
    actor_user_id: int | None
    task_id: UUID | None
    invoice_id: UUID | None
    idempotency_key: str
    comment: str | None
    metadata: Mapping[str, object]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class AufWalletOverview:
    wallet: AufWallet
    spent_30d_units: int
    recent_entries: tuple[AufWalletEntry, ...]


class AufWalletError(RuntimeError):
    pass


class AufWalletFrozen(AufWalletError):
    pass


class AufInsufficientBalance(AufWalletError):
    def __init__(self, *, required_units: int, available_units: int) -> None:
        self.required_units = int(required_units)
        self.available_units = int(available_units)
        super().__init__(
            "Недостаточно вельветов: нужно "
            f"{format_auf_units(self.required_units)}, доступно "
            f"{format_auf_units(self.available_units)}."
        )


def auf_to_units(value: Decimal | str | int) -> int:
    amount = Decimal(str(value)).quantize(_AUF_QUANT, rounding=ROUND_HALF_UP)
    return int(amount * AUF_SCALE)


def units_to_auf(value: int) -> Decimal:
    return (Decimal(int(value)) / Decimal(AUF_SCALE)).quantize(_AUF_QUANT)


def _velvet_currency_word(amount: Decimal) -> str:
    absolute = abs(amount)
    if absolute != absolute.to_integral_value():
        return "вельвета"
    number = int(absolute)
    if 11 <= number % 100 <= 14:
        return "вельветов"
    last_digit = number % 10
    if last_digit == 1:
        return "вельвет"
    if last_digit in {2, 3, 4}:
        return "вельвета"
    return "вельветов"


def format_auf_units(value: int, *, max_places: int = 2) -> str:
    amount = units_to_auf(value)
    rendered = f"{amount:.{max_places}f}".rstrip("0").rstrip(".")
    return f"{rendered} {_velvet_currency_word(amount)}"


def format_vl_units(value: int) -> str:
    units = int(value)
    if units % AUF_SCALE != 0:
        raise ValueError("Сумма VL должна быть целым числом вельветов.")
    return f"{units // AUF_SCALE} VL"


__all__ = (
    "AUF_SCALE",
    "AufEconomySettings",
    "AufInsufficientBalance",
    "AufWallet",
    "AufWalletEntry",
    "AufWalletError",
    "AufWalletFrozen",
    "AufWalletOperation",
    "AufWalletOverview",
    "AufWalletStatus",
    "auf_to_units",
    "format_auf_units",
    "format_vl_units",
    "units_to_auf",
)
