from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceQwenProductTests(unittest.TestCase):
    def test_migration_creates_isolated_checks_feedback_and_history(self) -> None:
        source = (ROOT / "migrations/z003_workspace_qwen_product.sql").read_text(
            encoding="utf-8"
        )
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_qwen_checks", source)
        self.assertIn("PRIMARY KEY (workspace_id, media_id)", source)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_qwen_feedback", source)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_qwen_jobs", source)
        self.assertIn("capture_workspace_qwen_feedback", source)

    def test_repository_claims_only_enabled_workspace_qwen_jobs(self) -> None:
        source = (
            ROOT / "velvet_bot/domains/workspaces/qwen_repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("JOIN workspace_modules AS module", source)
        self.assertIn("module.module_key = 'qwen'", source)
        self.assertIn("settings.qwen_enabled", source)
        self.assertIn("FOR UPDATE OF q SKIP LOCKED", source)
        self.assertIn("character.workspace_id = $1::BIGINT", source)

    def test_worker_uses_shared_local_ai_lock(self) -> None:
        source = (ROOT / "velvet_bot/app/workers.py").read_text(encoding="utf-8")
        self.assertIn("WorkspaceQwenQualityService", source)
        self.assertIn('name="workspace-qwen-quality"', source)
        self.assertIn("workspace_quality_service.process_once", source)
        self.assertIn("_run_ai_locked", source)

    def test_personal_qwen_menu_exposes_full_safe_workflows(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/workspace_qwen.py"
        ).read_text(encoding="utf-8")
        self.assertIn("🧠 Проверки архива", source)
        self.assertIn("📝 Промт ↔ результат", source)
        self.assertIn("🎨 Палитра и композиция", source)
        self.assertIn("🧬 Сравнение с референсом", source)
        self.assertIn("📜 История Qwen", source)
        self.assertIn('minimum_role: WorkspaceRole = "reviewer"', source)
        self.assertIn('"editor": 2', source)
        self.assertIn("_can_decide(membership)", source)

    def test_archive_card_has_qwen_button_and_early_handler(self) -> None:
        adjustment = (
            ROOT / "velvet_bot/presentation/telegram/workspace_ui_adjustments.py"
        ).read_text(encoding="utf-8")
        early_router = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/"
            "workspace_watermark_archive_only.py"
        ).read_text(encoding="utf-8")
        bundle = (
            ROOT / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        self.assertIn('text="🤖 Qwen-проверка"', adjustment)
        self.assertIn('"qwen"', adjustment)
        self.assertIn("register_workspace_qwen(router)", early_router)
        self.assertLess(
            bundle.index("router.include_router(workspace_watermark_archive_only_router)"),
            bundle.index("router.include_router(workspace_reference_library_router)"),
        )
        self.assertLess(
            bundle.index("router.include_router(workspace_watermark_archive_only_router)"),
            bundle.index("router.include_router(workspace_owner_controls_router)"),
        )

    def test_workspace_access_allows_qwen_callback_and_fsm(self) -> None:
        source = (ROOT / "velvet_bot/core/access/__init__.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"wq:"', source)
        self.assertIn('startswith("WorkspaceQwenForm:")', source)

    def test_decision_is_workspace_scoped_and_can_open_rework(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/workspace_qwen.py"
        ).read_text(encoding="utf-8")
        self.assertIn("workspace_id=workspace.id", source)
        self.assertIn("request_manual_rework", source)
        self.assertIn('decision = "accepted" if action == "accept" else "fix_required"', source)


if __name__ == "__main__":
    unittest.main()
