from __future__ import annotations

import unittest
from datetime import UTC, datetime
from pathlib import Path

from velvet_bot.domains.watermark.models import WatermarkJob, WatermarkRevision, WatermarkSettings, WatermarkWorkItem
from velvet_bot.domains.workspaces.models import Workspace
from velvet_bot.domains.workspaces.product_models import WorkspaceModuleSetting
from velvet_bot.presentation.telegram.routers.core_operations_controllers.workspace_product_experience import (
    _SHOW_BUTTON_HINTS,
    _home_keyboard_with_hint_toggle,
    _workspace_callback_with_template,
    _workspace_commands,
)
from velvet_bot.watermark_ui import build_watermark_keyboard

ROOT = Path(__file__).resolve().parents[1]


def _labels(keyboard) -> list[str]:
    return [button.text for row in keyboard.inline_keyboard for button in row]


def _workspace() -> Workspace:
    now = datetime.now(UTC)
    return Workspace(9, "private-9", "Мой архив", False, now, now)


def _modules() -> tuple[WorkspaceModuleSetting, ...]:
    now = datetime.now(UTC)
    return tuple(
        WorkspaceModuleSetting(
            workspace_id=9,
            module_key=key,  # type: ignore[arg-type]
            is_allowed=True,
            is_enabled=True,
            updated_by_user_id=1,
            created_at=now,
            updated_at=now,
        )
        for key in ("characters", "archive", "references", "watermark")
    )


def _watermark_item(status: str) -> WatermarkWorkItem:
    now = datetime.now(UTC)
    return WatermarkWorkItem(
        job=WatermarkJob(
            id=41,
            owner_user_id=1,
            chat_id=2,
            source_message_id=3,
            source_file_id="file",
            source_file_unique_id=None,
            source_path="source.png",
            status="active",
            current_revision=1,
            control_message_id=None,
            preview_message_id=None,
            final_path=None,
            created_at=now,
            updated_at=now,
            workspace_id=9,
        ),
        revision=WatermarkRevision(
            job_id=41,
            revision=1,
            settings=WatermarkSettings(),
            status=status,
            request_path=None,
            output_path=None,
            response_path=None,
            telegram_preview_file_id=None,
            error=None,
            created_at=now,
            completed_at=None,
        ),
    )


class WorkspaceCommandMenuTests(unittest.TestCase):
    def test_editor_gets_save_and_reference_commands(self) -> None:
        commands = {item.command for item in _workspace_commands("editor")}
        expected = {"archive", "save", "savecancel", "refs", "refadd", "refdel", "compare_ref"}
        self.assertTrue(expected.issubset(commands))

    def test_viewer_does_not_get_mutating_commands(self) -> None:
        commands = {item.command for item in _workspace_commands("viewer")}
        self.assertIn("archive", commands)
        self.assertIn("refs", commands)
        self.assertNotIn("save", commands)
        self.assertNotIn("refadd", commands)

    def test_template_callback_is_accepted_as_workspace_callback(self) -> None:
        self.assertTrue(_workspace_callback_with_template("wmtpl:show:9:"))


class WorkspaceHintToggleTests(unittest.TestCase):
    def test_home_can_hide_every_info_button_at_once(self) -> None:
        token = _SHOW_BUTTON_HINTS.set(False)
        try:
            keyboard = _home_keyboard_with_hint_toggle(
                _workspace(), public_enabled=False, modules=_modules()
            )
        finally:
            _SHOW_BUTTON_HINTS.reset(token)
        labels = _labels(keyboard)
        self.assertNotIn("ℹ️", labels)
        self.assertIn("ℹ️ Показать подсказки", labels)
        self.assertIn("🖼 Архив", labels)

    def test_home_keeps_help_buttons_until_hidden(self) -> None:
        token = _SHOW_BUTTON_HINTS.set(True)
        try:
            keyboard = _home_keyboard_with_hint_toggle(
                _workspace(), public_enabled=False, modules=_modules()
            )
        finally:
            _SHOW_BUTTON_HINTS.reset(token)
        labels = _labels(keyboard)
        self.assertIn("ℹ️", labels)
        self.assertIn("🙈 Скрыть все подсказки", labels)


class WatermarkDraftTests(unittest.TestCase):
    def test_draft_has_explicit_generate_button_and_no_approval(self) -> None:
        labels = _labels(build_watermark_keyboard(_watermark_item("draft")))
        self.assertIn("▶️ Сгенерировать preview", labels)
        self.assertNotIn("✅ Скачать PNG без сжатия", labels)
        self.assertNotIn("✅ Использовать watermark", labels)

    def test_processing_version_cannot_be_reconfigured(self) -> None:
        labels = _labels(build_watermark_keyboard(_watermark_item("processing")))
        self.assertIn("⏳ Генерация выполняется", labels)
        self.assertNotIn("▶️ Сгенерировать preview", labels)
        self.assertNotIn("Прозр. +", labels)

    def test_migration_allows_draft_and_hint_preference(self) -> None:
        migration = (ROOT / "migrations/915_workspace_commands_help_and_watermark_drafts.sql").read_text(encoding="utf-8")
        self.assertIn("show_button_hints", migration)
        self.assertIn("'draft'", migration)
        self.assertIn("watermark_revisions_status_check", migration)

    def test_product_router_runs_before_legacy_watermark_router(self) -> None:
        source = (ROOT / "velvet_bot/presentation/telegram/routers/core_operations_controllers/owner_menu.py").read_text(encoding="utf-8")
        self.assertLess(
            source.index("router.include_router(workspace_product_experience_router)"),
            source.index("router.include_router(watermark_router)"),
        )


if __name__ == "__main__":
    unittest.main()
