from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WorkspaceTaxonomyWatermarkReliabilityTests(unittest.TestCase):
    def test_migration_widens_character_taxonomy_and_adds_templates(self) -> None:
        source = (
            ROOT / "migrations/914_workspace_taxonomy_watermark_reliability.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("ALTER COLUMN category TYPE VARCHAR(64)", source)
        self.assertIn("ALTER COLUMN universe TYPE VARCHAR(64)", source)
        self.assertIn("ADD COLUMN IF NOT EXISTS emoji VARCHAR(16)", source)
        self.assertIn("CREATE TABLE IF NOT EXISTS workspace_watermark_templates", source)

    def test_personal_archive_shortcuts_are_explicit(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_taxonomy_admin.py"
        ).read_text(encoding="utf-8")
        self.assertIn('Command("myarchive", "archive_shortcuts")', source)
        self.assertIn("/save Имя или алиас персонажа", source)
        self.assertIn("/refs Имя или алиас персонажа", source)
        self.assertIn("/refadd Имя или алиас персонажа", source)

    def test_taxonomy_management_supports_name_emoji_and_delete(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_taxonomy_admin.py"
        ).read_text(encoding="utf-8")
        self.assertIn('text="✏️ Название"', source)
        self.assertIn('text="😀 Emoji"', source)
        self.assertIn('text="🗑 Удалить"', source)
        self.assertIn("UPDATE characters SET category = NULL", source)
        self.assertIn("SET universe = NULL, story_id = NULL", source)

    def test_watermark_template_is_applied_to_new_workspace_jobs(self) -> None:
        runtime = (
            ROOT
            / "velvet_bot/domains/watermark/workspace_template_runtime.py"
        ).read_text(encoding="utf-8")
        router_bundle = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        self.assertIn("WorkspaceWatermarkTemplateRepository", runtime)
        self.assertIn("settings=settings", runtime)
        self.assertIn("install_workspace_watermark_templates()", router_bundle)

    def test_standalone_personal_quick_watermark_is_removed(self) -> None:
        adjustment = (
            ROOT / "velvet_bot/presentation/telegram/workspace_ui_adjustments.py"
        ).read_text(encoding="utf-8")
        guard = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_watermark_archive_only.py"
        ).read_text(encoding="utf-8")
        self.assertIn('button.text != "⚡ Быстрый watermark"', adjustment)
        self.assertIn('F.action == "create"', guard)
        self.assertIn("запускается на карточке изображения в архиве", guard)

    def test_missing_personal_watermark_destination_uses_chat_fallback(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/archive_watermark_storage.py"
        ).read_text(encoding="utf-8")
        self.assertIn("_fallback_storage_settings", source)
        self.assertIn("configured or _fallback_storage_settings", source)
        self.assertIn("готовый PNG отправлен сюда", source)
        self.assertIn("_requeue_missing_output", source)


if __name__ == "__main__":
    unittest.main()
