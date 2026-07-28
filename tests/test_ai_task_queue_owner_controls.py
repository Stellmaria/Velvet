from __future__ import annotations

import unittest
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from velvet_bot.core.access import OWNER_ONLY_COMMANDS
from velvet_bot.core.ai_budget import AIBudgetScope
from velvet_bot.domains.ai_usage import (
    AITask,
    AITaskQueueSnapshot,
    AITaskStatus,
)
from velvet_bot.presentation.telegram.routers.core_operations_controllers.ai_queue import (
    _snapshot_text,
    _task_text,
)


class AITaskQueueOwnerFormattingTests(unittest.TestCase):
    def test_snapshot_shows_pause_and_counts(self) -> None:
        snapshot = AITaskQueueSnapshot(
            queued=3,
            running=2,
            success=10,
            error=1,
            cancelled=4,
            paused=True,
            pause_reason="server <maintenance>",
        )
        text = _snapshot_text(snapshot)
        self.assertIn("приостановлен", text)
        self.assertIn("Активных: <b>5</b>", text)
        self.assertIn("server &lt;maintenance&gt;", text)

    def test_task_text_contains_copyable_id_and_retry_state(self) -> None:
        task_id = uuid4()
        now = datetime(2026, 7, 28, 20, 30, tzinfo=timezone.utc)
        task = AITask(
            id=task_id,
            scope=AIBudgetScope.VISION,
            task_type="vision.semantic-profile",
            status=AITaskStatus.QUEUED,
            priority=50,
            payload={"media_id": 7},
            result={},
            dedupe_key="media:7",
            attempt_count=1,
            max_attempts=3,
            not_before=now,
            locked_by=None,
            locked_at=None,
            last_error_type="TimeoutError",
            last_error="provider <timeout>",
            last_retry_delay_seconds=60,
            estimated_cost_rub=Decimal("1.25"),
            created_by=100,
            created_at=now,
            updated_at=now,
            completed_at=None,
        )
        text = _task_text(task)
        self.assertIn(str(task_id), text)
        self.assertIn("1,25 ₽", text)
        self.assertIn("попытка 1/3", text)
        self.assertIn("retry 60 сек.", text)
        self.assertIn("provider &lt;timeout&gt;", text)

    def test_ai_queue_commands_are_owner_only(self) -> None:
        self.assertTrue(
            {
                "ai_queue",
                "ai_queue_retry",
                "ai_queue_cancel",
            }.issubset(OWNER_ONLY_COMMANDS)
        )


if __name__ == "__main__":
    unittest.main()
