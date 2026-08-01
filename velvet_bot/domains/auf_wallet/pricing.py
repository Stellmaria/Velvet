from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from html import escape
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
    global_markup_percent: Decimal
    user_markup_override_percent: Decimal | None
    markup_percent: Decimal
    quality_surcharge_velvets: int
    target_retail_usd: Decimal
    minimum_revenue_usd: Decimal
    billing_usd_to_rub: Decimal
    billing_usd_to_byn: Decimal
    quoted_units: int

    @property
    def quoted_auf(self) -> Decimal:
        return units_to_auf(self.quoted_units)

    @property
    def provider_cost_rub(self) -> Decimal:
        return self.provider_cost_usd * self.billing_usd_to_rub

    @property
    def provider_cost_byn(self) -> Decimal:
        return self.provider_cost_usd * self.billing_usd_to_byn

    @property
    def target_retail_rub(self) -> Decimal:
        return self.target_retail_usd * self.billing_usd_to_rub

    @property
    def target_retail_byn(self) -> Decimal:
        return self.target_retail_usd * self.billing_usd_to_byn

    @property
    def minimum_revenue_rub(self) -> Decimal:
        return self.minimum_revenue_usd * self.billing_usd_to_rub

    @property
    def minimum_revenue_byn(self) -> Decimal:
        return self.minimum_revenue_usd * self.billing_usd_to_byn

    @property
    def minimum_profit_usd(self) -> Decimal:
        return self.minimum_revenue_usd - self.provider_cost_usd

    @property
    def actual_markup_percent(self) -> Decimal:
        if self.provider_cost_usd <= 0:
            return Decimal("0")
        return self.minimum_profit_usd / self.provider_cost_usd * Decimal("100")


@dataclass(frozen=True, slots=True)
class AufUserMarkupPolicy:
    user_id: int
    global_markup_percent: Decimal
    override_markup_percent: Decimal | None

    @property
    def effective_markup_percent(self) -> Decimal:
        return (
            self.override_markup_percent
            if self.override_markup_percent is not None
            else self.global_markup_percent
        )


class AufPriceNotConfigured(ValueError):
    pass


class AufPricingRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def quote(self, payload: Mapping[str, object]) -> AufPriceQuote:
        async with self._database.acquire() as connection:
            return await quote_auf_payload(connection, payload)

    async def user_markup_policy(self, user_id: int) -> AufUserMarkupPolicy:
        async with self._database.acquire() as connection:
            return await _load_user_markup_policy(connection, int(user_id))

    async def set_user_markup(
        self,
        *,
        user_id: int,
        markup_percent: Decimal,
        actor_user_id: int,
    ) -> AufUserMarkupPolicy:
        normalized = _validate_markup_percent(markup_percent)
        async with self._database.acquire() as connection:
            await connection.execute(
                """
                INSERT INTO auf_user_markup_overrides (
                    user_id, markup_percent, updated_by_user_id
                )
                VALUES ($1::BIGINT, $2::NUMERIC, $3::BIGINT)
                ON CONFLICT (user_id) DO UPDATE
                SET markup_percent = EXCLUDED.markup_percent,
                    updated_by_user_id = EXCLUDED.updated_by_user_id,
                    updated_at = NOW()
                """,
                int(user_id),
                normalized,
                int(actor_user_id),
            )
            return await _load_user_markup_policy(connection, int(user_id))

    async def clear_user_markup(
        self,
        *,
        user_id: int,
    ) -> AufUserMarkupPolicy:
        async with self._database.acquire() as connection:
            await connection.execute(
                "DELETE FROM auf_user_markup_overrides WHERE user_id = $1::BIGINT",
                int(user_id),
            )
            return await _load_user_markup_policy(connection, int(user_id))


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
    user_id = _positive_int(payload.get("user_id"), default=0)

    row = await connection.fetchrow(
        """
        SELECT id, version_key, provider, model_alias, resolution, audio,
               pricing_basis, unit_cost_usd, extra_reference_cost_usd,
               quality_surcharge_velvets
        FROM auf_price_versions
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

    pricing_basis = str(row["pricing_basis"])
    unit_cost = Decimal(row["unit_cost_usd"])
    provider_cost = (
        unit_cost * Decimal(duration_seconds)
        if pricing_basis == "per_second"
        else unit_cost
    )
    extra_reference_cost = Decimal(row["extra_reference_cost_usd"])
    if extra_reference_cost > 0 and reference_count > 1:
        provider_cost += extra_reference_cost * Decimal(reference_count - 1)
    quality_surcharge_raw = (
        row.get("quality_surcharge_velvets", 0)
        if hasattr(row, "get")
        else 0
    )
    quality_surcharge_velvets = max(
        max(0, int(quality_surcharge_raw or 0)),
        _banana_quality_surcharge(model_alias, resolution),
    )

    settings = await connection.fetchrow(
        """
        SELECT retail_auf_usd, billing_usd_to_rub, billing_usd_to_byn,
               retail_markup_percent
        FROM auf_economy_settings
        WHERE singleton_id = 1
        """
    )
    if settings is None:
        raise RuntimeError("Настройки экономики Ауф не инициализированы.")
    retail_auf_usd = Decimal(settings["retail_auf_usd"])
    usd_to_rub = Decimal(settings["billing_usd_to_rub"])
    usd_to_byn = Decimal(settings["billing_usd_to_byn"])
    global_markup_percent = Decimal(settings["retail_markup_percent"])
    if retail_auf_usd <= 0 or usd_to_rub <= 0 or usd_to_byn <= 0:
        raise RuntimeError("Курсы и стоимость вельвета должны быть больше нуля.")
    _validate_markup_percent(global_markup_percent)

    user_markup_override: Decimal | None = None
    if user_id > 0:
        override_value = await connection.fetchval(
            """
            SELECT markup_percent
            FROM auf_user_markup_overrides
            WHERE user_id = $1::BIGINT
            """,
            user_id,
        )
        if override_value is not None:
            user_markup_override = _validate_markup_percent(Decimal(override_value))
    markup_percent = (
        user_markup_override
        if user_markup_override is not None
        else global_markup_percent
    )

    package_floor_rub = await connection.fetchval(
        """
        SELECT MIN(price_rub / package_auf::NUMERIC)
        FROM auf_package_prices
        WHERE is_active = TRUE
          AND effective_from <= NOW()
          AND (effective_to IS NULL OR effective_to > NOW())
        """
    )
    minimum_rub_per_auf = (
        Decimal(package_floor_rub)
        if package_floor_rub is not None
        else retail_auf_usd * usd_to_rub
    )
    if minimum_rub_per_auf <= 0:
        raise RuntimeError("Минимальная стоимость вельвета должна быть больше нуля.")

    markup_multiplier = Decimal("1") + markup_percent / Decimal("100")
    target_retail_usd = provider_cost * markup_multiplier
    target_retail_rub = target_retail_usd * usd_to_rub
    if _is_banana_model(model_alias):
        base_whole_velvets = _banana_base_whole_velvets(
            markup_percent=markup_percent,
            global_markup_percent=global_markup_percent,
        )
    else:
        base_whole_velvets = max(
            1,
            int(
                (target_retail_rub / minimum_rub_per_auf).to_integral_value(
                    rounding=ROUND_CEILING
                )
            ),
        )
    whole_velvets = base_whole_velvets + quality_surcharge_velvets
    quoted_units = whole_velvets * AUF_SCALE
    minimum_revenue_rub = minimum_rub_per_auf * Decimal(whole_velvets)
    minimum_revenue_usd = minimum_revenue_rub / usd_to_rub

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
        global_markup_percent=global_markup_percent,
        user_markup_override_percent=user_markup_override,
        markup_percent=markup_percent,
        quality_surcharge_velvets=quality_surcharge_velvets,
        target_retail_usd=target_retail_usd,
        minimum_revenue_usd=minimum_revenue_usd,
        billing_usd_to_rub=usd_to_rub,
        billing_usd_to_byn=usd_to_byn,
        quoted_units=quoted_units,
    )


async def _load_user_markup_policy(
    connection: Any,
    user_id: int,
) -> AufUserMarkupPolicy:
    global_markup = await connection.fetchval(
        """
        SELECT retail_markup_percent
        FROM auf_economy_settings
        WHERE singleton_id = 1
        """
    )
    if global_markup is None:
        raise RuntimeError("Настройки экономики Ауф не инициализированы.")
    override = await connection.fetchval(
        """
        SELECT markup_percent
        FROM auf_user_markup_overrides
        WHERE user_id = $1::BIGINT
        """,
        int(user_id),
    )
    return AufUserMarkupPolicy(
        user_id=int(user_id),
        global_markup_percent=_validate_markup_percent(Decimal(global_markup)),
        override_markup_percent=(
            _validate_markup_percent(Decimal(override))
            if override is not None
            else None
        ),
    )


def format_owner_price_details(quote: AufPriceQuote) -> str:
    """Render provider identity and real cost for an authorized Стэл view."""

    return (
        "<b>Себестоимость провайдера · только Стэл</b>\n"
        f"Провайдер: <code>{escape(quote.provider.upper())}</code>\n"
        f"Себестоимость: {_money_triplet(quote.provider_cost_usd, quote)}"
    )


def _money_triplet(usd: Decimal, quote: AufPriceQuote) -> str:
    rub = usd * quote.billing_usd_to_rub
    byn = usd * quote.billing_usd_to_byn
    return f"<b>${usd:.4f}</b> · <b>{rub:.2f} ₽ РФ</b> · <b>{byn:.2f} Br</b>"


def _banana_quality_surcharge(model_alias: str, resolution: str) -> int:
    if not _is_banana_model(model_alias):
        return 0
    return {"2K": 1, "4K": 2}.get(resolution.strip().upper(), 0)


def _is_banana_model(model_alias: str) -> bool:
    return model_alias in {"nano_banana_2", "nano_banana_pro"}


def _banana_base_whole_velvets(
    *,
    markup_percent: Decimal,
    global_markup_percent: Decimal,
) -> int:
    """Price both Banana models from the shared 1 VL global baseline."""

    effective_multiplier = Decimal("1") + markup_percent / Decimal("100")
    baseline_multiplier = Decimal("1") + global_markup_percent / Decimal("100")
    return max(
        1,
        int(
            (effective_multiplier / baseline_multiplier).to_integral_value(
                rounding=ROUND_CEILING
            )
        ),
    )


def _validate_markup_percent(value: Decimal) -> Decimal:
    normalized = Decimal(value).quantize(Decimal("0.01"))
    if not normalized.is_finite() or normalized < 0 or normalized > Decimal("1000"):
        raise ValueError("Наценка должна быть от 0 до 1000 процентов.")
    return normalized


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
    "AufUserMarkupPolicy",
    "format_owner_price_details",
    "quote_auf_payload",
)
