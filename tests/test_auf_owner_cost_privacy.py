from __future__ import annotations

import unittest
from decimal import Decimal

from velvet_bot.app.auf_owner_cost_privacy_install import (
    _owner_cost_block_from_values,
    _progress_text_for_user,
    _rewrite_owner_queue_confirmation,
    _strip_attempt_details,
)
from velvet_bot.domains.workspaces.product_models import GLOBAL_WORKSPACE_CREATOR_ID


class AufOwnerCostPrivacyTests(unittest.TestCase):
    def test_public_receipt_removes_every_attempt_line(self) -> None:
        text = (
            "<b>Ауф · результат</b>\n"
            "Попытка: <b>2/50</b>\n"
            "Повтор: <b>3/50</b>\n"
            "Успешная попытка: <b>4</b>\n"
            "Списано: <b>2 вельвета</b>"
        )

        public = _strip_attempt_details(text)

        self.assertNotIn("2/50", public)
        self.assertNotIn("3/50", public)
        self.assertNotIn("Успешная попытка", public)
        self.assertIn("Списано", public)

    def test_owner_cost_block_contains_only_provider_cost_currencies(self) -> None:
        block = _owner_cost_block_from_values(
            provider="kie",
            usd=Decimal("0.075"),
            rub=Decimal("6.750"),
            byn=Decimal("0.245"),
        )

        self.assertIn("без наценки", block)
        self.assertIn("$0.0750", block)
        self.assertIn("6.75 ₽ РФ", block)
        self.assertIn("0.24 Br", block)
        self.assertNotIn("VL", block)
        self.assertNotIn("вельвет", block.casefold())
        self.assertNotIn("прибыл", block.casefold())

    def test_owner_queue_confirmation_replaces_velvet_accounting(self) -> None:
        cost = _owner_cost_block_from_values(
            provider="grs",
            usd=Decimal("0.02"),
            rub=Decimal("1.80"),
            byn=Decimal("0.07"),
        )
        original = (
            "<b>Ауф · Nano Banana 2</b>\n\n"
            "Фото: <b>1</b>\n"
            "Зарезервировано: <b>2 VL</b>\n"
            "Задача: <code>123</code>"
        )

        owner = _rewrite_owner_queue_confirmation(original, cost)

        self.assertNotIn("VL", owner)
        self.assertNotIn("Зарезервировано", owner)
        self.assertIn("Себестоимость провайдера", owner)
        self.assertIn("$0.0200", owner)
        self.assertIn("Задача", owner)

    def test_progress_is_sanitized_for_user_but_preserved_for_stel(self) -> None:
        internal = (
            "Ожидаемая стоимость: <b>$0.02</b>\n"
            "Попытка: <b>2/50</b>"
        )

        public = _progress_text_for_user(
            internal,
            user_id=123,
            sanitizer=lambda _text: "PUBLIC",
        )
        owner = _progress_text_for_user(
            internal,
            user_id=GLOBAL_WORKSPACE_CREATOR_ID,
            sanitizer=lambda _text: "PUBLIC",
        )

        self.assertEqual("PUBLIC", public)
        self.assertEqual(internal, owner)


if __name__ == "__main__":
    unittest.main()
