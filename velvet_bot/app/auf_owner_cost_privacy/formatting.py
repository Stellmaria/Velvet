from __future__ import annotations

import re
from decimal import Decimal
from html import escape
from typing import Any, Callable

from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID

_ATTEMPT_LINE_RE = re.compile(
    r"(?mi)^(?:Попытка|Повтор|Успешная попытка):.*(?:\n|$)"
)


def is_global_owner(user_id: object) -> bool:
    try:
        return int(user_id or 0) == int(GLOBAL_WORKSPACE_CREATOR_ID)
    except (TypeError, ValueError):
        return False


def _money(value: Decimal, places: int) -> str:
    return f"{Decimal(value):.{places}f}"


def owner_cost_block_from_values(
    *,
    provider: str,
    usd: Decimal,
    rub: Decimal,
    byn: Decimal,
) -> str:
    return (
        "<b>Себестоимость провайдера · без наценки</b>\n"
        f"Маршрут: <code>{escape(str(provider).upper())}</code>\n"
        f"Списание: <b>${_money(usd, 4)}</b> · "
        f"<b>{_money(rub, 2)} ₽ РФ</b> · "
        f"<b>{_money(byn, 2)} Br</b>"
    )


def owner_cost_block(quote: Any) -> str:
    return owner_cost_block_from_values(
        provider=str(quote.provider),
        usd=Decimal(quote.provider_cost_usd),
        rub=Decimal(quote.provider_cost_rub),
        byn=Decimal(quote.provider_cost_byn),
    )


def strip_attempt_details(text: str) -> str:
    """Remove retry counters from every product-facing result receipt."""

    return re.sub(r"\n{3,}", "\n\n", _ATTEMPT_LINE_RE.sub("", str(text))).strip()


def rewrite_owner_queue_confirmation(text: str, cost_block: str) -> str:
    """Replace owner-only VL accounting lines with provider cost."""

    lines = str(text).splitlines()
    rewritten: list[str] = []
    inserted = False
    for line in lines:
        normalized = line.strip().casefold()
        is_price_line = normalized.startswith(
            (
                "зарезервировано:",
                "учётная цена:",
                "списание стэл:",
            )
        )
        if is_price_line:
            if not inserted:
                rewritten.extend(cost_block.splitlines())
                inserted = True
            continue
        rewritten.append(line)
    if not inserted:
        return str(text)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(rewritten)).strip()


def progress_text_for_user(
    text: str,
    *,
    user_id: object,
    sanitizer: Callable[[str], str],
) -> str:
    if is_global_owner(user_id):
        return str(text)
    return sanitizer(str(text))


__all__ = (
    "is_global_owner",
    "owner_cost_block",
    "owner_cost_block_from_values",
    "progress_text_for_user",
    "rewrite_owner_queue_confirmation",
    "strip_attempt_details",
)
