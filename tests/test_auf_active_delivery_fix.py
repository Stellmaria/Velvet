from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from velvet_bot.app.auf_active_delivery_fix import (
    provider_task_id,
    task_card_keyboard,
    task_card_text,
)
from velvet_bot.app.composition import build_application_composition
from velvet_bot.presentation.telegram.routers.workspace_auf import AufCallback


def _row(*, status: str = "success") -> dict[str, object]:
    return {
        "id": uuid4(),
        "status": status,
        "payload": {
            "request": {
                "model": "nano_banana_pro",
                "input_mode": "photo_text",
                "resolution": "2K",
                "duration_seconds": 6,
            }
        },
        "created_at": datetime(2026, 7, 30, 4, 12),
        "completed_at": datetime(2026, 7, 30, 4, 13),
        "quoted_units": 0,
        "charge_status": None,
    }


class AufActiveDeliveryFixTests(unittest.TestCase):
    def test_provider_task_id_uses_campaign_runtime_when_result_is_empty(self) -> None:
        self.assertEqual(
            "grs:provider-task",
            provider_task_id(
                {},
                {
                    "kie_campaign": {
                        "last_provider_task_id": "grs:provider-task",
                    }
                },
            ),
        )

    def test_success_image_is_rendered_as_one_clear_card(self) -> None:
        row = _row()
        text = task_card_text(row=row, offset=0)

        self.assertIn("Последняя задача", text)
        self.assertIn("Nano Banana Pro", text)
        self.assertIn("Тип: <b>Изображение</b>", text)
        self.assertIn("Режим: <b>Фото + текст</b>", text)
        self.assertIn("Качество: <b>2K</b>", text)
        self.assertIn(str(row["id"])[:8], text)
        self.assertIn("Получить результат", text)
        self.assertIn("Новая генерация и новое списание не запускаются", text)
        self.assertNotIn("6 сек", text)
        self.assertNotIn("без операции Ауф", text)

    def test_success_card_has_one_unambiguous_result_button(self) -> None:
        row = _row()
        markup = task_card_keyboard(
            row=row,
            workspace_id=1,
            offset=2,
            has_older=True,
        )

        labels = [button.text for line in markup.inline_keyboard for button in line]
        self.assertEqual(1, labels.count("📥 Получить результат"))
        self.assertIn("← Новее", labels)
        self.assertIn("Старее →", labels)
        self.assertIn("🔄 Обновить карточку", labels)
        self.assertNotIn("📤 Доставить · Nano Banana Pro", labels)

        delivery = markup.inline_keyboard[0][0]
        parsed = AufCallback.unpack(delivery.callback_data or "")
        self.assertEqual("deliver", parsed.action)
        self.assertEqual(str(row["id"]), parsed.value)
        self.assertLessEqual(len(delivery.callback_data or ""), 64)

    def test_unfinished_task_does_not_offer_result(self) -> None:
        markup = task_card_keyboard(
            row=_row(status="running"),
            workspace_id=1,
            offset=0,
            has_older=False,
        )
        labels = [button.text for line in markup.inline_keyboard for button in line]
        self.assertNotIn("📥 Получить результат", labels)
        self.assertIn("🔄 Обновить карточку", labels)

    def test_fix_is_installed_after_delivery_recovery(self) -> None:
        stage_names = build_application_composition().stage_names
        recovery_install = stage_names.index("install_auf_result_delivery_recovery")
        active = stage_names.index("install_auf_active_delivery_fix")
        self.assertLess(recovery_install, active)

        fix_source = Path("velvet_bot/app/auf_active_delivery_fix.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("active_worker = workers.KieGenerationWorker", fix_source)
        self.assertIn("active_worker.install_delivery_handler", fix_source)
        self.assertIn("recovery.install_redelivery_handler", fix_source)
        self.assertIn("portal.install_user_tasks_renderer", fix_source)
        self.assertNotIn("active_worker._deliver_best_effort", fix_source)
        self.assertNotIn("portal._render_user_tasks", fix_source)


if __name__ == "__main__":
    unittest.main()
