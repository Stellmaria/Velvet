from __future__ import annotations

import ast
import asyncio
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.application.owner_profiles import (
    delete_alias_from_text,
    set_prompt_from_text,
)
from velvet_bot.application.owner_references import (
    finish_reference_upload,
    parse_reference_index,
)
from velvet_bot.reference_uploads import ReferenceUploadSessions


class Phase9ArchitectureTests(unittest.TestCase):
    def test_owner_actions_does_not_import_other_handlers(self) -> None:
        path = Path("velvet_bot/handlers/owner_actions.py")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        self.assertFalse(
            {name for name in imported if name.startswith("velvet_bot.handlers.")}
        )

    def test_application_layer_does_not_import_aiogram(self) -> None:
        violations: list[str] = []
        for path in Path("velvet_bot/application").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    if node.module == "aiogram" or node.module.startswith("aiogram."):
                        violations.append(f"{path}:{node.lineno}")
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "aiogram" or alias.name.startswith("aiogram."):
                            violations.append(f"{path}:{node.lineno}")
        self.assertEqual(violations, [])

    def test_owner_actions_no_longer_fakes_command_objects(self) -> None:
        source = Path("velvet_bot/handlers/owner_actions.py").read_text(encoding="utf-8")
        self.assertNotIn("SimpleNamespace", source)
        self.assertNotIn("CommandObject", source)
        self.assertNotIn("model_copy(", source)


class Phase9UseCaseTests(unittest.TestCase):
    def test_reference_index_supports_multiword_character_names(self) -> None:
        self.assertEqual(parse_reference_index("Тёмный Аид #12"), ("Тёмный Аид", 12))

    def test_reference_session_finish_is_transport_independent(self) -> None:
        sessions = ReferenceUploadSessions()
        sessions.start(44, character_id=7, character_name="Аид")
        session = finish_reference_upload(sessions, user_id=44)
        self.assertIsNotNone(session)
        self.assertEqual(session.character_name, "Аид")
        self.assertIsNone(finish_reference_upload(sessions, user_id=44))

    def test_prompt_off_is_normalized_by_use_case(self) -> None:
        character = SimpleNamespace(id=7, name="Аид")
        database = SimpleNamespace(get_character=AsyncMock(return_value=character))
        with unittest.mock.patch(
            "velvet_bot.application.owner_profiles.set_character_prompt_url",
            new=AsyncMock(),
        ) as setter:
            result = asyncio.run(set_prompt_from_text(database, "Аид off"))
        self.assertIsNone(result.value)
        setter.assert_awaited_once_with(
            database,
            character_id=7,
            prompt_post_url=None,
        )

    def test_alias_delete_keeps_multiword_name(self) -> None:
        character = SimpleNamespace(id=9, name="Каэль Лэнг")
        database = SimpleNamespace(get_character=AsyncMock(return_value=character))
        with unittest.mock.patch(
            "velvet_bot.application.owner_profiles.delete_character_alias",
            new=AsyncMock(return_value=True),
        ) as delete_alias:
            result = asyncio.run(delete_alias_from_text(database, "Каэль Лэнг KaelLang"))
        self.assertTrue(result.deleted)
        delete_alias.assert_awaited_once_with(
            database,
            character_id=9,
            alias="KaelLang",
        )


if __name__ == "__main__":
    unittest.main()
