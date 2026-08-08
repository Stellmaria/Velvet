from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from velvet_bot.ai_quality import AIQualitySummary
from velvet_bot.domains.media_quality.models import DuplicatePage
from velvet_bot.domains.media_rework import MediaReworkSummary
from velvet_bot.domains.media_quality.reset_repository import DuplicateResetRepository
from velvet_bot.quality_audit import QualitySummary
from velvet_bot.quality_operations import QualityOperationsRepository
from velvet_bot.quality_ui import QualityCallback, build_duplicate_list, build_quality_dashboard
from velvet_bot.velvet_ai_ui import build_velvet_ai_menu


class _AsyncContext:
    def __init__(self, value) -> None:
        self.value = value

    async def __aenter__(self):
        return self.value

    async def __aexit__(self, exc_type, exc, traceback) -> bool:
        return False


class QwenDuplicateRetryControlTests(unittest.IsolatedAsyncioTestCase):
    async def test_qwen_retry_builds_quality_only_plan_without_semantic_mutation(self) -> None:
        now = datetime.now(timezone.utc)
        candidates = [
            {"media_id": 31, "candidate_kind": "failed"},
            {"media_id": 29, "candidate_kind": "failed"},
        ]
        plan_row = {
            "id": 8,
            "requested_by": 42,
            "kind": "errors",
            "requested_limit": 10,
            "media_ids": [31, 29],
            "new_count": 0,
            "legacy_pending_count": 0,
            "failed_count": 2,
            "created_at": now,
            "expires_at": now + timedelta(minutes=15),
            "started_at": None,
            "started_count": None,
        }
        connection = SimpleNamespace(
            execute=AsyncMock(return_value="DELETE 0"),
            fetch=AsyncMock(return_value=candidates),
            fetchrow=AsyncMock(return_value=plan_row),
            transaction=Mock(return_value=_AsyncContext(None)),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        plan = await QualityOperationsRepository(database).plan_errors(
            requested_by=42,
            limit=10,
        )

        self.assertEqual(plan.media_ids, (31, 29))
        self.assertEqual(plan.failed_count, 2)
        candidate_sql = connection.fetch.await_args.args[0]
        self.assertIn("media_ai_quality_checks", candidate_sql)
        self.assertNotIn("media_ai_profiles", candidate_sql)
        self.assertIn("status IN ('error', 'skipped')", candidate_sql)
        executed_sql = "\n".join(
            str(call.args[0]) for call in connection.execute.await_args_list
        )
        self.assertNotIn("media_ai_profiles", executed_sql)
        self.assertNotIn("UPDATE media_ai_quality_checks", executed_sql)

    async def test_duplicate_reset_clears_results_and_requeues_available_media(self) -> None:
        connection = SimpleNamespace(
            execute=AsyncMock(side_effect=["DELETE 5", "DELETE 8", "UPDATE 13"]),
            transaction=Mock(return_value=_AsyncContext(None)),
        )
        database = SimpleNamespace(acquire=Mock(return_value=_AsyncContext(connection)))

        result = await DuplicateResetRepository(database).reset_all()

        self.assertEqual(result.candidates_deleted, 5)
        self.assertEqual(result.fingerprints_deleted, 8)
        self.assertEqual(result.media_reset, 13)
        self.assertEqual(connection.execute.await_count, 3)
        for call in connection.execute.await_args_list:
            self.assertEqual(call.args[-1], 20 * 1024 * 1024)
            self.assertIn("preview_file_id IS NOT NULL", call.args[0])

    def test_qwen_panel_exposes_retry_and_audit_links_to_panel(self) -> None:
        summary = QualitySummary(
            pending_duplicates=0,
            confirmed_duplicates=0,
            pending_scans=0,
            scan_errors=0,
            broken_files=0,
            unchecked_files=0,
            missing_category=0,
            missing_universe=0,
            missing_story=0,
            empty_characters=0,
            media_without_prompt=0,
            orphan_media=0,
            unresolved_hashtags=0,
        )
        ai_summary = AIQualitySummary(
            pending=0,
            processing=0,
            ready=0,
            errors=2,
            skipped=1,
            unreviewed=0,
            accepted=0,
            fix_required=0,
            clean=0,
            warnings=0,
            critical=0,
        )
        rework_summary = MediaReworkSummary(
            active=0,
            needs_fix=0,
            checking=0,
            ready_for_review=0,
            stel_priority=0,
            qwen_only=0,
        )

        _, audit_keyboard = build_quality_dashboard(summary, ai_summary)
        _, qwen_keyboard = build_velvet_ai_menu(
            enabled=True,
            provider="ollama",
            model="qwen3-vl:8b",
            quality=ai_summary,
            rework=rework_summary,
        )
        audit_actions = {
            QualityCallback.unpack(button.callback_data).action
            for row in audit_keyboard.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("quality:")
        }
        qwen_actions = {
            QualityCallback.unpack(button.callback_data).action
            for row in qwen_keyboard.inline_keyboard
            for button in row
            if button.callback_data and button.callback_data.startswith("quality:")
        }

        self.assertIn("ai_menu", audit_actions)
        self.assertIn("quality_retry_errors", qwen_actions)

    def test_duplicate_list_exposes_confirmed_full_reset(self) -> None:
        page = DuplicatePage(items=(), page=0, page_size=6, total_items=0)

        _, keyboard = build_duplicate_list(page, status="pending")
        actions = {
            QualityCallback.unpack(button.callback_data).action
            for row in keyboard.inline_keyboard
            for button in row
            if button.callback_data
        }

        self.assertIn("dupresetask", actions)


if __name__ == "__main__":
    unittest.main()
