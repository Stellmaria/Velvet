from __future__ import annotations

import unittest
from decimal import Decimal

from velvet_bot.app.auf_generation_privacy_install import (
    _remove_attempt_details,
    _remove_owner_velvet_details,
    format_owner_real_costs,
    public_generation_stage,
)
from velvet_bot.domains.auf_wallet.pricing import AufPriceQuote


class AufGenerationPrivacyTests(unittest.TestCase):
    @staticmethod
    def _quote() -> AufPriceQuote:
        return AufPriceQuote(
            price_version_id=1,
            version_key="test-v1",
            provider="grs",
            model_alias="nano_banana_pro",
            resolution="2K",
            audio=None,
            duration_seconds=6,
            reference_count=1,
            provider_cost_usd=Decimal("0.2500"),
            markup_percent=Decimal("20"),
            target_retail_usd=Decimal("0.3000"),
            minimum_revenue_usd=Decimal("0.3200"),
            billing_usd_to_rub=Decimal("80"),
            billing_usd_to_byn=Decimal("3"),
            quoted_units=40000,
        )

    def test_public_stage_hides_attempts_provider_and_failure_reason(self) -> None:
        self.assertEqual(
            "Генерация выполняется.",
            public_generation_stage("Платная попытка 2/50: отправка в Kie.ai."),
        )
        self.assertEqual(
            "Ошибка генерации.",
            public_generation_stage(
                "Экономная кампания остановлена без нового повтора: NSFW policy refusal"
            ),
        )

    def test_owner_real_costs_use_three_currencies_without_velvets(self) -> None:
        text = format_owner_real_costs(self._quote())
        self.assertIn("$0.2500", text)
        self.assertIn("20.00 ₽ РФ", text)
        self.assertIn("0.75 Br", text)
        self.assertIn("+20%", text)
        self.assertNotIn("вельвет", text.casefold())
        self.assertNotIn("ауф", text.casefold())

    def test_user_receipt_removes_attempt_details(self) -> None:
        text = _remove_attempt_details(
            "Готово\nУспешная попытка: <b>2</b>\nСписано: <b>4 вельвета</b>"
        )
        self.assertNotIn("попыт", text.casefold())
        self.assertIn("4 вельвета", text)

    def test_owner_confirmation_removes_internal_velvet_accounting(self) -> None:
        text = _remove_owner_velvet_details(
            "Задача поставлена\nУчётная цена: <b>4 вельвета</b>\n"
            "Списание Стэл: <b>0 вельветов</b>\nЗадача: <code>abc</code>"
        )
        self.assertNotIn("вельвет", text.casefold())
        self.assertIn("Задача: <code>abc</code>", text)


if __name__ == "__main__":
    unittest.main()
