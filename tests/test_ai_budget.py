from __future__ import annotations

import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.core.ai_budget import (
    AIBudgetGuard,
    AIBudgetPolicy,
    AIBudgetScope,
    AIUsageSnapshot,
    load_ai_budget_policy,
)


class AIBudgetGuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = AIBudgetPolicy(
            enabled=True,
            daily_limit_rub=Decimal("500"),
            monthly_limit_rub=Decimal("5000"),
            max_request_rub=Decimal("250"),
            hermes_reserve_rub=Decimal("300"),
        )
        self.guard = AIBudgetGuard(self.policy)

    def test_allows_request_inside_limits(self) -> None:
        decision = self.guard.evaluate(
            scope=AIBudgetScope.VISION,
            estimated_cost_rub=Decimal("12.34"),
            usage=AIUsageSnapshot(
                today_rub=Decimal("100"),
                month_rub=Decimal("1000"),
            ),
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.daily_remaining_rub, Decimal("387.66"))
        self.assertEqual(decision.monthly_remaining_rub, Decimal("3687.66"))

    def test_preserves_hermes_reserve_for_regular_requests(self) -> None:
        decision = self.guard.evaluate(
            scope=AIBudgetScope.ROLEPLAY,
            estimated_cost_rub=Decimal("1"),
            usage=AIUsageSnapshot(
                today_rub=Decimal("10"),
                month_rub=Decimal("4700"),
            ),
        )
        self.assertFalse(decision.allowed)
        self.assertIn("резерв Hermes", decision.reason)

    def test_hermes_can_use_reserved_budget(self) -> None:
        decision = self.guard.evaluate(
            scope=AIBudgetScope.HERMES,
            estimated_cost_rub=Decimal("100"),
            usage=AIUsageSnapshot(
                today_rub=Decimal("10"),
                month_rub=Decimal("4700"),
            ),
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.monthly_remaining_rub, Decimal("200.00"))

    def test_rejects_request_over_single_request_limit(self) -> None:
        decision = self.guard.evaluate(
            scope=AIBudgetScope.CODEX,
            estimated_cost_rub=Decimal("251"),
            usage=AIUsageSnapshot(),
        )
        self.assertFalse(decision.allowed)
        self.assertIn("одного запроса", decision.reason)

    def test_reports_highest_reached_warning_threshold(self) -> None:
        decision = self.guard.evaluate(
            scope=AIBudgetScope.HERMES,
            estimated_cost_rub=Decimal("100"),
            usage=AIUsageSnapshot(month_rub=Decimal("4200")),
        )
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.warning_percent, 85)

    def test_load_policy_from_environment(self) -> None:
        environment = {
            "AI_BUDGET_ENABLED": "true",
            "AI_DAILY_BUDGET_RUB": "600,50",
            "AI_MONTHLY_BUDGET_RUB": "7000",
            "AI_MAX_REQUEST_RUB": "300",
            "AI_HERMES_RESERVE_RUB": "400",
            "AI_BUDGET_WARNING_PERCENTS": "60,80,95",
        }
        with patch.dict(os.environ, environment, clear=True):
            policy = load_ai_budget_policy()
        self.assertEqual(policy.daily_limit_rub, Decimal("600.50"))
        self.assertEqual(policy.monthly_limit_rub, Decimal("7000.00"))
        self.assertEqual(policy.warning_percents, (60, 80, 95))


if __name__ == "__main__":
    unittest.main()
