from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from velvet_bot.app.auf_active_delivery_fix import (
    _delivery_buttons_for_all_success,
    _provider_task_id,
)


class AufActiveDeliveryFixTests(unittest.TestCase):
    def test_provider_task_id_uses_campaign_runtime_when_result_is_empty(self) -> None:
        self.assertEqual(
            "grs:provider-task",
            _provider_task_id(
                {},
                {
                    "kie_campaign": {
                        "last_provider_task_id": "grs:provider-task",
                    }
                },
            ),
        )

    def test_success_task_gets_delivery_button_without_saved_url(self) -> None:
        task_id = uuid4()
        portal = SimpleNamespace(
            _MODEL_NAMES={"nano_banana_pro": "Nano Banana Pro"}
        )
        rows = _delivery_buttons_for_all_success(
            portal=portal,
            page=[
                {
                    "id": task_id,
                    "status": "success",
                    "payload": {
                        "request": {"model": "nano_banana_pro"},
                    },
                }
            ],
            results={task_id: {"result_urls": []}},
            workspace_id=1,
        )
        self.assertEqual(1, len(rows))
        self.assertIn("Доставить", rows[0][0].text)
        self.assertLessEqual(len(rows[0][0].callback_data or ""), 64)

    def test_fix_is_installed_after_delivery_recovery(self) -> None:
        app_source = Path("velvet_bot/app/__init__.py").read_text(encoding="utf-8")
        recovery = app_source.index("install_auf_result_delivery_recovery()")
        active = app_source.index("install_auf_active_delivery_fix()")
        self.assertLess(recovery, active)

        fix_source = Path("velvet_bot/app/auf_active_delivery_fix.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("active_worker = workers.KieGenerationWorker", fix_source)
        self.assertIn(
            "active_worker._deliver_best_effort = recovery._deliver_record_with_recovery",
            fix_source,
        )


if __name__ == "__main__":
    unittest.main()
