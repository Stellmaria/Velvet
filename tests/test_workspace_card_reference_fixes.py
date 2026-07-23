from __future__ import annotations

import unittest
from pathlib import Path

from velvet_bot.app.reference_sessions import ReferenceUploadSessions

ROOT = Path(__file__).resolve().parents[1]


class WorkspaceCreationAccessRegressionTests(unittest.TestCase):
    def test_first_workspace_name_is_allowed_before_workspace_exists(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/middleware/access.py"
        ).read_text(encoding="utf-8")

        self.assertIn("_workspace_creation_name_form_is_active", source)
        self.assertIn('endswith(":waiting_workspace_name")', source)
        self.assertIn("or await _has_active_personal_workspace", source)


class WorkspaceCardTextContractTests(unittest.TestCase):
    def test_character_prompt_is_removed_and_alias_is_explained(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/workspace_ui_adjustments.py"
        ).read_text(encoding="utf-8")

        self.assertIn("Алиас — дополнительное имя персонажа", source)
        self.assertIn('button.text not in {"📝 Промт", "📝 Ссылка на промт"}', source)
        self.assertNotIn("Supervisor, Git, Codex", source)

    def test_material_help_is_last_and_describes_only_material_actions(self) -> None:
        source = (
            ROOT / "velvet_bot/presentation/telegram/workspace_ui_adjustments.py"
        ).read_text(encoding="utf-8")

        self.assertIn("rows.insert(max(0, len(rows) - 1), help_row)", source)
        self.assertIn("Справка по кнопкам материала", source)
        self.assertIn("Отправить на доработку", source)
        self.assertNotIn("+ Создать персонажа", source)
        self.assertNotIn("пакетную загрузку", source)


class WorkspaceReferenceButtonContractTests(unittest.TestCase):
    def test_reference_sessions_can_pin_a_replacement(self) -> None:
        sessions = ReferenceUploadSessions()

        session = sessions.start(
            42,
            character_id=7,
            character_name="Каэль",
            workspace_id=5,
            replace_reference_id=11,
            replace_offset=2,
        )

        self.assertEqual(11, session.replace_reference_id)
        self.assertEqual(2, session.replace_offset)
        self.assertEqual(session, sessions.get(42))

    def test_personal_reference_cards_have_add_replace_and_delete_buttons(self) -> None:
        source = (
            ROOT
            / "velvet_bot/presentation/telegram/routers/workspace_reference_buttons.py"
        ).read_text(encoding="utf-8")

        for label in (
            "➕ Добавить референс",
            "🔄 Заменить этот",
            "🗑 Удалить референс",
            "✅ Завершить",
        ):
            self.assertIn(label, source)
        repository = (
            ROOT / "velvet_bot/domains/references/repository.py"
        ).read_text(encoding="utf-8")
        self.assertIn("async def replace(", repository)
        self.assertIn("AND id <> $4::BIGINT", repository)


if __name__ == "__main__":
    unittest.main()
