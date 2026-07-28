from __future__ import annotations

import unittest
from decimal import Decimal
from unittest.mock import patch

from velvet_bot.domains.ai_usage.pricing import AITokenPricing, load_token_pricing


class AITokenPricingTests(unittest.TestCase):
    def test_calculates_input_and_output_cost(self) -> None:
        pricing = AITokenPricing(
            input_rub_per_million=Decimal("10"),
            output_rub_per_million=Decimal("20"),
        )
        self.assertEqual(
            pricing.cost(input_tokens=1_000_000, output_tokens=500_000),
            Decimal("20.0000"),
        )

    def test_rounds_nonzero_cost_up_to_ledger_precision(self) -> None:
        pricing = AITokenPricing(
            input_rub_per_million=Decimal("1"),
            output_rub_per_million=Decimal("0"),
        )
        self.assertEqual(
            pricing.cost(input_tokens=1, output_tokens=0),
            Decimal("0.0001"),
        )

    def test_loads_rates_from_prefixed_environment(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AI_TEXT_INPUT_RUB_PER_1M": "12,5",
                "AI_TEXT_OUTPUT_RUB_PER_1M": "25",
            },
            clear=False,
        ):
            pricing = load_token_pricing("AI_TEXT")
        self.assertEqual(pricing.input_rub_per_million, Decimal("12.5"))
        self.assertEqual(pricing.output_rub_per_million, Decimal("25"))

    def test_rejects_unpriced_enabled_model(self) -> None:
        with patch.dict(
            "os.environ",
            {
                "AI_TEXT_INPUT_RUB_PER_1M": "",
                "AI_TEXT_OUTPUT_RUB_PER_1M": "",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                load_token_pricing("AI_TEXT")


if __name__ == "__main__":
    unittest.main()
