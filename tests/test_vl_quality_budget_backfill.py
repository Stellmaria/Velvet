from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.ai_quality import build_quality_vision_contract


ROOT = Path(__file__).resolve().parents[1]


class VLQualityBudgetBackfillTests(unittest.TestCase):
    def test_quality_contract_uses_bounded_output_budget(self) -> None:
        contract = build_quality_vision_contract()
        self.assertEqual(512, contract.max_output_tokens)

        source = (ROOT / "velvet_bot/ai_quality.py").read_text(encoding="utf-8")
        self.assertIn('"num_predict": 512', source)
        self.assertIn('"max_tokens": 512', source)
        self.assertNotIn('"num_predict": 1700', source)
        self.assertNotIn('"max_tokens": 1700', source)

    def test_claim_keeps_legacy_sql_literal_without_executing_mass_seed(self) -> None:
        source = (ROOT / "velvet_bot/ai_quality.py").read_text(encoding="utf-8")
        self.assertIn(
            "Retain tracked SQL literal until #463 migration without executing it",
            source,
        )
        self.assertNotIn("await asyncio.sleep(0, result=(", source)
        self.assertNotIn(
            'await connection.execute(\n                    """\n                    INSERT INTO media_ai_quality_checks',
            source,
        )
        self.assertIn("safe_attempts = max(1, min(int(max_attempts), 1))", source)


if __name__ == "__main__":
    unittest.main()
