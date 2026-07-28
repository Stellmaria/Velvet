from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_UP

_COST_QUANTUM = Decimal("0.0001")
_TOKENS_PER_MILLION = Decimal("1000000")


@dataclass(frozen=True, slots=True)
class AITokenPricing:
    input_rub_per_million: Decimal
    output_rub_per_million: Decimal

    def __post_init__(self) -> None:
        for name, value in (
            ("input_rub_per_million", self.input_rub_per_million),
            ("output_rub_per_million", self.output_rub_per_million),
        ):
            if not value.is_finite() or value < 0:
                raise ValueError(f"{name} должен быть неотрицательной конечной суммой.")

    @property
    def configured(self) -> bool:
        return self.input_rub_per_million > 0 or self.output_rub_per_million > 0

    def cost(self, *, input_tokens: int, output_tokens: int) -> Decimal:
        if input_tokens < 0 or output_tokens < 0:
            raise ValueError("Количество токенов не может быть отрицательным.")
        total = (
            Decimal(input_tokens) * self.input_rub_per_million
            + Decimal(output_tokens) * self.output_rub_per_million
        ) / _TOKENS_PER_MILLION
        if total == 0:
            return Decimal("0")
        return total.quantize(_COST_QUANTUM, rounding=ROUND_UP)


def load_token_pricing(prefix: str) -> AITokenPricing:
    normalized = prefix.strip().upper()
    if not normalized:
        raise ValueError("Префикс AI-pricing не может быть пустым.")
    input_name = f"{normalized}_INPUT_RUB_PER_1M"
    output_name = f"{normalized}_OUTPUT_RUB_PER_1M"
    pricing = AITokenPricing(
        input_rub_per_million=_parse_rate(os.getenv(input_name, ""), input_name),
        output_rub_per_million=_parse_rate(os.getenv(output_name, ""), output_name),
    )
    if not pricing.configured:
        raise RuntimeError(
            f"Для включённой модели задайте {input_name} и/или {output_name}; "
            "запросы без известной цены запрещены."
        )
    return pricing


def _parse_rate(value: str, variable_name: str) -> Decimal:
    cleaned = value.strip().replace(",", ".")
    if not cleaned:
        return Decimal("0")
    try:
        result = Decimal(cleaned)
    except InvalidOperation as error:
        raise RuntimeError(
            f"{variable_name} должен содержать цену в рублях за 1 млн токенов."
        ) from error
    if not result.is_finite() or result < 0:
        raise RuntimeError(
            f"{variable_name} должен быть неотрицательной конечной суммой."
        )
    return result


__all__ = ("AITokenPricing", "load_token_pricing")
