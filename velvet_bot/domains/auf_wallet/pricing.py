from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from velvet_bot.database import Database

from .models import AUF_SCALE, units_to_auf


@dataclass(frozen=True, slots=True)
class AufPriceQuote:
    price_version_id: int
    version_key: str
    provider: str
    model_alias: str
    resolution: str
    audio: bool | None
    duration_seconds: int
    reference_count: int
    provider_cost_usd: Decimal
    quoted_units: int

    @property
    def quoted_auf(self) -> Decimal:
        return units_to_auf(self.quoted_units)


class AufPriceNotConfigured(ValueError):
    pass


class AufPricingRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def quote(self, payload: Mapping[str, object]) -> AufPriceQuote:
        async with self._database.acquire() as connection:
            return await quote_auf_payload(connection, payload)


async def quote_auf_payload(
    connection: Any,
    payload: Mapping[str, object],
) -> AufPriceQuote:
    request_value = payload.get("request")
    if not isinstance(request_value, Mapping):
        raise AufPriceNotConfigured("В AI-задаче отсутствуют параметры генерации.")

    model_alias = str(request_value.get("model") or "").strip()
    resolution = str(request_value.get("resolution") or "").strip()
    if not model_alias:
        raise AufPriceNotConfigured("В AI-задаче не указана модель генерации.")

    extra_input = request_value.get("extra_input")
    extra = dict(extra_input) if isinstance(extra_input, Mapping) else {}
    audio: bool | None = (
        bool(extra.get("generate_audio", False))
        if model_alias == "seedance_15_pro_video"
        else None
    )
    duration_seconds = _positive_int(request_value.get("duration_seconds"), default=6)
    references = request_value.get("references")
    reference_count = len(references) if isinstance(references, (list, tuple)) else 0

    row = await connection.fetchrow(
        """
        SELECT id, version_key, provider, model_alias, resolution, audio,
               pricing_basis, unit_cost_usd, extra_reference_cost_usd
        FROM meow_price_versions
        WHERE model_alias = $1::VARCHAR
          AND operation = 'media.generate'
          AND effective_from <= NOW()
          AND (effective_to IS NULL OR effective_to > NOW())
          AND (resolution = $2::VARCHAR OR resolution IS NULL)
          AND (audio IS NOT DISTINCT FROM $3::BOOLEAN OR audio IS NULL)
        ORDER BY
            CASE WHEN resolution = $2::VARCHAR THEN 0 ELSE 1 END,
            CASE WHEN audio IS NOT DISTINCT FROM $3::BOOLEAN THEN 0 ELSE 1 END,
            effective_from DESC,
            id DESC
        LIMIT 1
        """,
        model_alias,
        resolution or None,
        audio,
    )
    if row is None:
        suffix = f" · {resolution}" if resolution else ""
        raise AufPriceNotConfigured(
            f"Для модели {model_alias}{suffix} не настроена цена Ауф."
        )

    settings = await connection.fetchrow(
        """
        SELECT provider_auf_usd
        FROM meow_economy_settings
        WHERE singleton_id = 1
        """
    )
    if settings is None:
        raise RuntimeError("Настройки экономики Ауф не инициализированы.")
    provider_auf_usd = Decimal(settings["provider_auf_usd"])
    if provider_auf_usd <= 0:
        raise RuntimeError("Покрытие API одного Ауф должно быть больше нуля.")

    unit_cost = Decimal(row["unit_cost_usd"])
    provider_cost = (
        unit_cost * Decimal(duration_seconds)
        if str(row["pricing_basis"]) == "per_second"
        else unit_cost
    )
    extra_reference_cost = Decimal(row["extra_reference_cost_usd"])
    if extra_reference_cost > 0 and reference_count > 1:
        provider_cost += extra_reference_cost * Decimal(reference_count - 1)

    quoted_units = int(
        (
            provider_cost
            / provider_auf_usd
            * Decimal(AUF_SCALE)
        ).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    )
    if quoted_units <= 0:
        raise RuntimeError("Расчётная цена генерации в Ауф получилась нулевой.")

    return AufPriceQuote(
        price_version_id=int(row["id"]),
        version_key=str(row["version_key"]),
        provider=str(row["provider"]),
        model_alias=model_alias,
        resolution=resolution,
        audio=audio,
        duration_seconds=duration_seconds,
        reference_count=reference_count,
        provider_cost_usd=provider_cost,
        quoted_units=quoted_units,
    )


def _positive_int(value: object, *, default: int) -> int:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


__all__ = (
    "AufPriceNotConfigured",
    "AufPriceQuote",
    "AufPricingRepository",
    "quote_auf_payload",
)
