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
    minimum_user_markup_percent: Decimal
    markup_percent: Decimal
    pricing_strategy: str
    target_margin_percent: Decimal
    minimum_contribution_margin_percent: Decimal
    allow_subsidized_generations: bool
    operational_cost_buffer_percent: Decimal
    subsidy_guard_applied: bool
    quote_rub_per_vl: Decimal
    quality_surcharge_velvets: int
    minimum_velvets: int
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
    def operational_reserve_usd(self) -> Decimal:
        return (
            self.provider_cost_usd
            * self.operational_cost_buffer_percent
            / Decimal("100")
        )

    @property
    def buffered_cost_usd(self) -> Decimal:
        return self.provider_cost_usd + self.operational_reserve_usd

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
        return self.minimum_revenue_usd - self.buffered_cost_usd

    @property
    def actual_markup_percent(self) -> Decimal:
        if self.provider_cost_usd <= 0:
            return Decimal("0")
        return self.minimum_profit_usd / self.provider_cost_usd * Decimal("100")

    @property
    def contribution_margin_percent(self) -> Decimal:
        if self.minimum_revenue_usd <= 0:
            return Decimal("0")
        return (
            self.minimum_profit_usd
            / self.minimum_revenue_usd
            * Decimal("100")
        )


@dataclass(frozen=True, slots=True)
class AufUserMarkupPolicy:
    user_id: int
    global_markup_percent: Decimal
    override_markup_percent: Decimal | None
    minimum_user_markup_percent: Decimal

    @property
    def effective_markup_percent(self) -> Decimal:
        if self.override_markup_percent is None:
            return self.global_markup_percent
        return max(
            self.override_markup_percent,
            self.minimum_user_markup_percent,
        )


@dataclass(frozen=True, slots=True)
class _PricingSettings:
    retail_auf_usd: Decimal
    usd_to_rub: Decimal
    usd_to_byn: Decimal
    global_markup_percent: Decimal
    quote_rub_per_vl: Decimal
    operational_reserve_percent: Decimal
    minimum_user_markup_percent: Decimal
    pricing_strategy: str
    target_margin_percent: Decimal
    minimum_contribution_margin_percent: Decimal
    allow_subsidized_generations: bool


@dataclass(frozen=True, slots=True)
class _PricingTarget:
    strategy: str
    markup_percent: Decimal
    target_retail_usd: Decimal
    subsidy_guard_applied: bool


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
            current_policy = await _load_user_markup_policy(
                connection, int(user_id)
            )
            minimum_normalized = current_policy.minimum_user_markup_percent
            if normalized < minimum_normalized:
                raise ValueError(
                    "Индивидуальная наценка не может быть ниже "
                    f"{minimum_normalized:.2f}%."
                )
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
    request = _request_payload(payload)
    model_alias = str(request.get("model") or "").strip()
    resolution = str(request.get("resolution") or "").strip()
    if not model_alias:
        raise AufPriceNotConfigured("В AI-задаче не указана модель генерации.")

    audio = _request_audio(model_alias, request)
    duration_seconds = _positive_int(request.get("duration_seconds"), default=6)
    reference_count = _reference_count(request)
    user_id = _positive_int(payload.get("user_id"), default=0)
    row = await _load_price_version(
        connection,
        model_alias=model_alias,
        resolution=resolution,
        audio=audio,
    )
    provider_cost = _provider_cost(
        row,
        duration_seconds=duration_seconds,
        reference_count=reference_count,
    )
    quality_surcharge, standard_floor, discounted_floor = _price_floors(row)
    settings = await _load_pricing_settings(connection)
    user_override = await _load_user_markup_override(connection, user_id=user_id)
    target = _pricing_target(
        provider_cost_usd=provider_cost,
        settings=settings,
        user_markup_override=user_override,
    )
    minimum_velvets = _minimum_velvets(
        standard=standard_floor,
        discounted=discounted_floor,
        user_override=user_override,
        effective_markup=target.markup_percent,
        minimum_user_markup=settings.minimum_user_markup_percent,
    )
    whole_velvets = _whole_velvets(
        target_retail_usd=target.target_retail_usd,
        usd_to_rub=settings.usd_to_rub,
        quote_rub_per_vl=settings.quote_rub_per_vl,
        quality_surcharge=quality_surcharge,
        minimum_velvets=minimum_velvets,
    )
    minimum_revenue_usd = (
        settings.quote_rub_per_vl
        * Decimal(whole_velvets)
        / settings.usd_to_rub
    )

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
        global_markup_percent=settings.global_markup_percent,
        user_markup_override_percent=user_override,
        minimum_user_markup_percent=settings.minimum_user_markup_percent,
        markup_percent=target.markup_percent,
        pricing_strategy=target.strategy,
        target_margin_percent=settings.target_margin_percent,
        minimum_contribution_margin_percent=(
            settings.minimum_contribution_margin_percent
        ),
        allow_subsidized_generations=settings.allow_subsidized_generations,
        operational_cost_buffer_percent=settings.operational_reserve_percent,
        subsidy_guard_applied=target.subsidy_guard_applied,
        quote_rub_per_vl=settings.quote_rub_per_vl,
        quality_surcharge_velvets=quality_surcharge,
        minimum_velvets=minimum_velvets,
        target_retail_usd=target.target_retail_usd,
        minimum_revenue_usd=minimum_revenue_usd,
        billing_usd_to_rub=settings.usd_to_rub,
        billing_usd_to_byn=settings.usd_to_byn,
        quoted_units=whole_velvets * AUF_SCALE,
    )


def _request_payload(payload: Mapping[str, object]) -> Mapping[str, object]:
    request = payload.get("request")
    if not isinstance(request, Mapping):
        raise AufPriceNotConfigured("В AI-задаче отсутствуют параметры генерации.")
    return request


def _request_audio(
    model_alias: str,
    request: Mapping[str, object],
) -> bool | None:
    if model_alias != "seedance_15_pro_video":
        return None
    raw_extra = request.get("extra_input")
    extra = dict(raw_extra) if isinstance(raw_extra, Mapping) else {}
    return bool(extra.get("generate_audio", False))


def _reference_count(request: Mapping[str, object]) -> int:
    references = request.get("references")
    return len(references) if isinstance(references, (list, tuple)) else 0


async def _load_price_version(
    connection: Any,
    *,
    model_alias: str,
    resolution: str,
    audio: bool | None,
) -> Any:
    row = await connection.fetchrow(
        """
        SELECT id, version_key, provider, model_alias, resolution, audio,
               pricing_basis, unit_cost_usd, extra_reference_cost_usd,
               quality_surcharge_velvets, minimum_velvets,
               minimum_discounted_velvets
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
    return row


def _provider_cost(
    row: Any,
    *,
    duration_seconds: int,
    reference_count: int,
) -> Decimal:
    unit_cost = Decimal(row["unit_cost_usd"])
    cost = (
        unit_cost * Decimal(duration_seconds)
        if str(row["pricing_basis"]) == "per_second"
        else unit_cost
    )
    extra_reference_cost = Decimal(row["extra_reference_cost_usd"])
    if extra_reference_cost > 0 and reference_count > 1:
        cost += extra_reference_cost * Decimal(reference_count - 1)
    return cost


async def _load_pricing_settings(connection: Any) -> _PricingSettings:
    row = await connection.fetchrow(
        """
        SELECT retail_auf_usd, billing_usd_to_rub, billing_usd_to_byn,
               retail_markup_percent, quote_rub_per_vl,
               minimum_user_markup_percent, pricing_strategy,
               target_margin_percent, minimum_contribution_margin_percent,
               allow_subsidized_generations,
               auf_effective_operational_reserve_percent()
                   AS effective_operational_reserve_percent
        FROM auf_economy_settings
        WHERE singleton_id = 1
        """
    )
    if row is None:
        raise RuntimeError("Настройки экономики Ауф не инициализированы.")
    strategy = str(row["pricing_strategy"])
    if strategy not in {"markup", "target_margin"}:
        raise RuntimeError("Неизвестная стратегия расчёта цены Ауф.")
    settings = _PricingSettings(
        retail_auf_usd=Decimal(row["retail_auf_usd"]),
        usd_to_rub=Decimal(row["billing_usd_to_rub"]),
        usd_to_byn=Decimal(row["billing_usd_to_byn"]),
        global_markup_percent=_validate_markup_percent(
            Decimal(row["retail_markup_percent"])
        ),
        quote_rub_per_vl=Decimal(row["quote_rub_per_vl"]),
        operational_reserve_percent=_validate_markup_percent(
            Decimal(row["effective_operational_reserve_percent"])
        ),
        minimum_user_markup_percent=_validate_markup_percent(
            Decimal(row["minimum_user_markup_percent"])
        ),
        pricing_strategy=strategy,
        target_margin_percent=_validate_margin_percent(
            Decimal(row["target_margin_percent"]),
            label="Целевая маржа",
        ),
        minimum_contribution_margin_percent=_validate_margin_percent(
            Decimal(row["minimum_contribution_margin_percent"]),
            label="Минимальная маржа",
        ),
        allow_subsidized_generations=bool(row["allow_subsidized_generations"]),
    )
    if (
        settings.retail_auf_usd <= 0
        or settings.usd_to_rub <= 0
        or settings.usd_to_byn <= 0
        or settings.quote_rub_per_vl <= 0
    ):
        raise RuntimeError("Курсы и расчётная стоимость VL должны быть больше нуля.")
    return settings


async def _load_user_markup_override(
    connection: Any,
    *,
    user_id: int,
) -> Decimal | None:
    if user_id <= 0:
        return None
    value = await connection.fetchval(
        """
        SELECT markup_percent
        FROM auf_user_markup_overrides
        WHERE user_id = $1::BIGINT
        """,
        user_id,
    )
    return _validate_markup_percent(Decimal(value)) if value is not None else None


def _pricing_target(
    *,
    provider_cost_usd: Decimal,
    settings: _PricingSettings,
    user_markup_override: Decimal | None,
) -> _PricingTarget:
    buffered_cost = provider_cost_usd * (
        Decimal("1") + settings.operational_reserve_percent / Decimal("100")
    )
    markup = settings.global_markup_percent
    strategy = settings.pricing_strategy
    if user_markup_override is not None:
        markup = max(
            user_markup_override,
            settings.minimum_user_markup_percent,
        )
        strategy = "user_markup"
        target = buffered_cost * (Decimal("1") + markup / Decimal("100"))
    elif strategy == "target_margin":
        target = buffered_cost / (
            Decimal("1") - settings.target_margin_percent / Decimal("100")
        )
    else:
        target = buffered_cost * (Decimal("1") + markup / Decimal("100"))

    guard_applied = False
    if not settings.allow_subsidized_generations:
        guardrail = buffered_cost / (
            Decimal("1")
            - settings.minimum_contribution_margin_percent / Decimal("100")
        )
        if target < guardrail:
            target = guardrail
            guard_applied = True
    return _PricingTarget(
        strategy=strategy,
        markup_percent=markup,
        target_retail_usd=target,
        subsidy_guard_applied=guard_applied,
    )


def _minimum_velvets(
    *,
    standard: int,
    discounted: int | None,
    user_override: Decimal | None,
    effective_markup: Decimal,
    minimum_user_markup: Decimal,
) -> int:
    if (
        user_override is not None
        and effective_markup == minimum_user_markup
        and discounted is not None
    ):
        return discounted
    return standard


def _whole_velvets(
    *,
    target_retail_usd: Decimal,
    usd_to_rub: Decimal,
    quote_rub_per_vl: Decimal,
    quality_surcharge: int,
    minimum_velvets: int,
) -> int:
    cost_based = max(
        1,
        int(
            (target_retail_usd * usd_to_rub / quote_rub_per_vl).to_integral_value(
                rounding=ROUND_CEILING
            )
        ),
    )
    return max(minimum_velvets, cost_based + quality_surcharge)


def _price_floors(row: Any) -> tuple[int, int, int | None]:
    getter = row.get if hasattr(row, "get") else None
    quality_raw = getter("quality_surcharge_velvets", 0) if getter else 0
    standard_raw = getter("minimum_velvets", 1) if getter else 1
    discounted_raw = getter("minimum_discounted_velvets") if getter else None
    return (
        max(0, int(quality_raw or 0)),
        max(1, int(standard_raw or 1)),
        max(1, int(discounted_raw)) if discounted_raw is not None else None,
    )


async def _load_user_markup_policy(
    connection: Any,
    user_id: int,
) -> AufUserMarkupPolicy:
    settings = await connection.fetchrow(
        """
        SELECT retail_markup_percent, minimum_user_markup_percent
        FROM auf_economy_settings
        WHERE singleton_id = 1
        """
    )
    if settings is None:
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
        global_markup_percent=_validate_markup_percent(
            Decimal(settings["retail_markup_percent"])
        ),
        override_markup_percent=(
            _validate_markup_percent(Decimal(override))
            if override is not None
            else None
        ),
        minimum_user_markup_percent=_validate_markup_percent(
            Decimal(settings["minimum_user_markup_percent"])
        ),
    )


def format_owner_price_details(quote: AufPriceQuote) -> str:
    """Render provider identity and real economics for an authorized Стэл view."""

    guard = (
        "\nЗащита от субсидии: <b>подняла цену до минимальной маржи</b>"
        if quote.subsidy_guard_applied
        else ""
    )
    return (
        "<b>Экономика генерации · только Стэл</b>\n"
        f"Провайдер: <code>{escape(quote.provider.upper())}</code>\n"
        f"Себестоимость: {_money_triplet(quote.provider_cost_usd, quote)}\n"
        f"Резерв: <b>{quote.operational_cost_buffer_percent:.2f}%</b> · "
        f"{_money_triplet(quote.operational_reserve_usd, quote)}\n"
        f"Стратегия: <code>{escape(quote.pricing_strategy)}</code> · "
        f"целевая маржа <b>{quote.target_margin_percent:.2f}%</b>\n"
        f"Маржа после округления: "
        f"<b>{quote.contribution_margin_percent:.2f}%</b>"
        f"{guard}"
    )


def _money_triplet(usd: Decimal, quote: AufPriceQuote) -> str:
    rub = usd * quote.billing_usd_to_rub
    byn = usd * quote.billing_usd_to_byn
    return f"<b>${usd:.4f}</b> · <b>{rub:.2f} ₽ РФ</b> · <b>{byn:.2f} Br</b>"


def _validate_markup_percent(value: Decimal) -> Decimal:
    normalized = Decimal(value).quantize(Decimal("0.01"))
    if not normalized.is_finite() or normalized < 0 or normalized > Decimal("1000"):
        raise ValueError("Наценка должна быть от 0 до 1000 процентов.")
    return normalized


def _validate_margin_percent(value: Decimal, *, label: str) -> Decimal:
    normalized = Decimal(value).quantize(Decimal("0.01"))
    if not normalized.is_finite() or normalized < 0 or normalized >= Decimal("100"):
        raise ValueError(f"{label} должна быть от 0 до 99.99 процента.")
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
