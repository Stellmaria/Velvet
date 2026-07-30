from __future__ import annotations

from collections.abc import Mapping

from velvet_bot.domains.auf_wallet.pricing import (
    AufPriceNotConfigured,
    AufPriceQuote,
)


def validate_expected_auf_quote(
    payload: Mapping[str, object],
    quote: AufPriceQuote,
) -> None:
    """Reject a charge when the user-confirmed quote no longer matches the catalog."""

    expected_version = str(
        payload.get("auf_expected_price_version") or ""
    ).strip()
    expected_units_value = payload.get("auf_expected_quoted_units")
    if not expected_version and expected_units_value is None:
        return
    try:
        expected_units = int(str(expected_units_value or "0").strip())
    except (TypeError, ValueError) as error:
        raise AufPriceNotConfigured(
            "Подтверждённая цена Ауф повреждена. Откройте финальный экран снова."
        ) from error
    if expected_version != quote.version_key or expected_units != quote.quoted_units:
        raise AufPriceNotConfigured(
            "Цена Ауф изменилась. Вернитесь к финальному экрану и подтвердите новую сумму."
        )


__all__ = ("validate_expected_auf_quote",)
