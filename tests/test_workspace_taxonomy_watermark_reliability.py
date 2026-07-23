from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.presentation.telegram.routers.workspace_watermark_archive_only import (
    _download_policy_error,
    _watermark_prerequisite_error,
)


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

    def test_watermark_entry_does_not_require_a_storage_destination(self) -> None:
        self.assertIsNone(
            _watermark_prerequisite_error(module_enabled=True, has_asset=True)
        )
        self.assertEqual(
            "Сначала включите модуль watermark и загрузите шаблон.",
            _watermark_prerequisite_error(module_enabled=False, has_asset=True),
        )
        self.assertEqual(
            "Сначала загрузите шаблон watermark.",
            _watermark_prerequisite_error(module_enabled=True, has_asset=False),
        )

    def test_watermark_download_policy_needs_asset_but_not_storage(self) -> None:
        self.assertIsNone(
            _download_policy_error(
                audience="all",
                variant="watermark",
                channel_kinds=set(),
                has_watermark_asset=True,
            )
        )
        self.assertEqual(
            "Сначала загрузите шаблон watermark.",
            _download_policy_error(
                audience="all",
                variant="watermark",
                channel_kinds=set(),
                has_watermark_asset=False,
            ),
        )
        self.assertEqual(
            "Сначала подключите канал «Проверка скачивания».",
            _download_policy_error(
                audience="subscribers",
                variant="original",
                channel_kinds=set(),
                has_watermark_asset=False,
            ),
        )

    def test_fallback_router_precedes_generic_owner_controls(self) -> None:
        bundle = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/archive_and_public.py"
        ).read_text(encoding="utf-8")
        fallback = "router.include_router(workspace_watermark_archive_only_router)"
        generic = "router.include_router(workspace_owner_controls_router)"
        self.assertLess(bundle.index(fallback), bundle.index(generic))


if __name__ == "__main__":
    unittest.main()
