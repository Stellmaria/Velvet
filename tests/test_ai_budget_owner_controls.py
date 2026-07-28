from __future__ import annotations

import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

from velvet_bot.core.access import OWNER_ONLY_COMMANDS
from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import AIBudgetStatus, AIUsageEvent
from velvet_bot.presentation.telegram.routers.core_operations_controllers.ai_budget import (
    _budget_status_text,
    _event_text,
    _format_rub,
)


class AIBudgetOwnerFormattingTests(unittest.TestCase):
    def test_formats_russian_rubles(self) -> None:
        self.assertEqual("1 234,50 ₽", _format_rub(Decimal("1234.5")))

    def test_budget_status_contains_limits_pause_and_warning(self) -> None:
        status = AIBudgetStatus(
            enabled=True,
            daily_limit_rub=Decimal("500"),
            monthly_limit_rub=Decimal("5000"),
            max_request_rub=Decimal("250"),
            hermes_reserve_rub=Decimal("300"),
            today_rub=Decimal("12.5"),
            month_rub=Decimal("3500"),
            reserved_today_rub=Decimal("2"),
            reserved_month_rub=Decimal("25"),
            daily_remaining_rub=Decimal("485.5"),
            ordinary_month_remaining_rub=Decimal("1175"),
            total_month_remaining_rub=Decimal("1475"),
            paused=True,
            pause_reason="проверка <сервера>",
            updated_by=100,
            updated_at=datetime.now(timezone.utc),
            warning_month=date(2026, 7, 1),
            warning_percent=70,
        )
        text = _budget_status_text(status)
        self.assertIn("AI-бюджет Velvet", text)
        self.assertIn("приостановлен", text)
        self.assertIn("проверка &lt;сервера&gt;", text)
        self.assertIn("3 500,00 ₽", text)
        self.assertIn("70%", text)

    def test_usage_event_is_compact_and_escaped(self) -> None:
        event = AIUsageEvent(
            request_id=uuid4(),
            scope=AIBudgetScope.ROLEPLAY,
            provider="openai_compatible",
            model="model<unsafe>",
            operation="roleplay.reply",
            status="success",
            estimated_cost_rub=Decimal("1"),
            actual_cost_rub=Decimal("0.42"),
            input_tokens=100,
            output_tokens=200,
            latency_ms=850,
            user_id=10,
            chat_id=20,
            created_at=datetime(2026, 7, 28, 18, 30, tzinfo=timezone.utc),
            completed_at=datetime(2026, 7, 28, 18, 30, tzinfo=timezone.utc),
        )
        text = _event_text(event)
        self.assertIn("roleplay", text)
        self.assertIn("model&lt;unsafe&gt;", text)
        self.assertIn("0,42 ₽", text)
        self.assertIn("300 ток.", text)
        self.assertIn("850 мс", text)

    def test_ai_budget_commands_are_owner_only(self) -> None:
        self.assertTrue(
            {
                "ai_budget",
                "ai_usage",
                "ai_pause",
                "ai_resume",
            }.issubset(OWNER_ONLY_COMMANDS)
        )


if __name__ == "__main__":
    unittest.main()
