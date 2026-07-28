from __future__ import annotations

from decimal import Decimal

from velvet_bot.audit import TelegramAuditLogger
from velvet_bot.database import Database
from velvet_bot.domains.ai_usage import AIBudgetWarning, AIUsageService, build_ai_usage_service


def _format_rub(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}".replace(".", ",") + " ₽"


def build_audited_ai_usage_service(
    *,
    database: Database,
    audit_logger: TelegramAuditLogger,
) -> AIUsageService:
    async def send_budget_warning(warning: AIBudgetWarning) -> None:
        await audit_logger.send(
            "AI-бюджет достиг порога",
            level="WARNING",
            threshold=f"{warning.threshold_percent}%",
            month_spend=_format_rub(warning.month_rub),
            monthly_limit=_format_rub(warning.monthly_limit_rub),
            remaining=_format_rub(warning.remaining_rub),
            period=warning.period_start.isoformat(),
        )

    return build_ai_usage_service(
        database=database,
        warning_handler=send_budget_warning,
    )


__all__ = ("build_audited_ai_usage_service",)
