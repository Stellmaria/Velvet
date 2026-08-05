from __future__ import annotations

import importlib
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from velvet_bot.app.auf_generation_receipt_install import (
    AufGenerationReceipt,
    append_receipt_to_task_card,
    append_receipt_to_task_line,
    build_public_result_caption,
    format_generation_elapsed,
    receipt_from_task_row,
)
from velvet_bot.app.composition import build_application_composition
from velvet_bot.domains.auf_wallet import (
    auf_to_units,
    build_auf_charged_task_queue_service,
)
from velvet_bot.domains.media_generation import (
    KieGenerationRequest,
    KieInputMode,
    KieModelAlias,
)

ROOT = Path(__file__).resolve().parents[1]


class AufGenerationReceiptTests(unittest.TestCase):
    def test_production_bootstrap_is_replaced_with_charged_queue(self) -> None:
        installer = importlib.import_module("velvet_bot.app.auf_charged_queue_install")
        bootstrap = importlib.import_module("velvet_bot.app.bootstrap")
        original = bootstrap.build_ai_task_queue_service
        original_installed = installer._INSTALLED
        try:
            installer._INSTALLED = False
            installer.install_auf_charged_queue()
            self.assertIs(
                bootstrap.build_ai_task_queue_service,
                build_auf_charged_task_queue_service,
            )
        finally:
            bootstrap.build_ai_task_queue_service = original
            installer._INSTALLED = original_installed

    def test_runtime_composition_installs_charging_before_receipts(self) -> None:
        stage_names = build_application_composition().stage_names
        charged_queue = stage_names.index("install_auf_charged_queue")
        receipts = stage_names.index("install_auf_generation_receipts")
        branding = stage_names.index("install_auf_branding")
        self.assertNotIn("install_auf_grs_brand", stage_names)
        self.assertLess(charged_queue, receipts)
        self.assertLess(receipts, branding)

    def test_receipt_uses_total_elapsed_provider_attempt_and_capture(self) -> None:
        created = datetime(2026, 7, 30, 16, 0, tzinfo=timezone.utc)
        row = {
            "id": uuid4(),
            "status": "success",
            "payload": {"auf_expected_quoted_units": auf_to_units("1.5")},
            "result": {"provider_attempt_count": 2},
            "attempt_count": 3,
            "created_at": created,
            "completed_at": created + timedelta(seconds=84),
            "quoted_units": auf_to_units("1.5"),
            "captured_units": auf_to_units("1.5"),
            "charge_status": "captured",
        }
        receipt = receipt_from_task_row(row)
        self.assertEqual(84, receipt.elapsed_seconds)
        self.assertEqual(2, receipt.successful_attempt)
        self.assertEqual(auf_to_units("1.5"), receipt.captured_units)
        self.assertEqual("captured", receipt.charge_status)

    def test_public_caption_is_a_receipt_without_provider_secrets(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_2,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="1K",
        )
        caption = build_public_result_caption(
            request,
            AufGenerationReceipt(
                elapsed_seconds=84,
                successful_attempt=2,
                quoted_units=auf_to_units("1"),
                captured_units=auf_to_units("1"),
                charge_status="captured",
            ),
        )
        self.assertIn("Время генерации: <b>1 мин 24 сек</b>", caption)
        self.assertIn("Успешная попытка: <b>2</b>", caption)
        self.assertIn("Списано: <b>1 вельвет</b>", caption)
        self.assertNotIn("GRS", caption)
        self.assertNotIn("Kie", caption)
        self.assertNotIn("Провайдер", caption)
        self.assertNotIn("Задача провайдера", caption)
        self.assertNotIn("grs:", caption)

    def test_service_generation_reports_zero_charge(self) -> None:
        request = KieGenerationRequest(
            model=KieModelAlias.NANO_BANANA_2,
            input_mode=KieInputMode.TEXT,
            prompt="portrait",
            resolution="1K",
        )
        caption = build_public_result_caption(
            request,
            AufGenerationReceipt(
                elapsed_seconds=5,
                successful_attempt=1,
                quoted_units=auf_to_units("1"),
                charge_status="",
            ),
        )
        self.assertIn("Списание: <b>0 вельветов · служебная генерация</b>", caption)

    def test_task_views_show_elapsed_time_and_successful_attempt(self) -> None:
        created = datetime(2026, 7, 30, 16, 0, tzinfo=timezone.utc)
        row = {
            "status": "success",
            "payload": {},
            "result": {"provider_attempt_count": 3},
            "attempt_count": 4,
            "created_at": created,
            "completed_at": created + timedelta(seconds=125),
            "quoted_units": 0,
            "captured_units": 0,
            "charge_status": "",
        }
        card = append_receipt_to_task_card(
            "Карточка\n\nНажмите кнопку.",
            row,
        )
        line = append_receipt_to_task_line("• задача", row)
        self.assertIn("Время генерации: <b>2 мин 5 сек</b>", card)
        self.assertIn("Успешная попытка: <b>3</b>", card)
        self.assertIn("время 2 мин 5 сек · попытка 3", line)

    def test_elapsed_formatter_handles_short_and_long_runs(self) -> None:
        self.assertEqual("менее 1 сек", format_generation_elapsed(0))
        self.assertEqual("59 сек", format_generation_elapsed(59))
        self.assertEqual("1 мин", format_generation_elapsed(60))
        self.assertEqual("1 ч 1 мин 1 сек", format_generation_elapsed(3661))

    def test_workspace_task_queries_expose_receipt_fields(self) -> None:
        source = (ROOT / "velvet_bot/application/workspace_tasks.py").read_text(
            encoding="utf-8"
        )
        for field in (
            "task.result",
            "task.attempt_count",
            "task.completed_at",
            "charge.captured_units",
            "charge.status AS charge_status",
        ):
            self.assertIn(field, source)


if __name__ == "__main__":
    unittest.main()
