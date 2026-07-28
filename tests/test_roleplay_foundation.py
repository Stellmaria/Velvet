from __future__ import annotations

import os
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from velvet_bot.core.config.roleplay import load_roleplay_settings
from velvet_bot.domains.roleplay import (
    RoleplayCharacter,
    RoleplayCharacterDraft,
    RoleplayContextBudget,
    RoleplayMessage,
    build_roleplay_context,
    normalize_roleplay_name,
    validate_character_draft,
)
from velvet_bot.services.roleplay_ollama import (
    OllamaRoleplayClient,
    RoleplayGenerationOptions,
)


ROOT = Path(__file__).resolve().parents[1]


def _character() -> RoleplayCharacter:
    now = datetime.now(UTC)
    return RoleplayCharacter(
        id=1,
        owner_user_id=1001,
        name="Аид",
        normalized_name="аид",
        adult_confirmed=True,
        age_text="взрослый, 25+",
        pronouns="он/его",
        appearance={"eyes": "золотые", "hair": "чёрные"},
        personality={"temperament": "сдержанный"},
        speech={"style": "лаконичный"},
        biography={"origin": "подземный мир"},
        behavior_rules={"user_control": "не управлять пользователем"},
        canonical_facts=("не покидает роль",),
        example_dialogue=("«Я слушаю.»",),
        system_notes=None,
        version=1,
        created_at=now,
        updated_at=now,
    )


class RoleplayFoundationTests(unittest.TestCase):
    def test_character_name_is_separate_and_normalized(self) -> None:
        display, normalized = normalize_roleplay_name("  Аид   RP  ")
        self.assertEqual("Аид RP", display)
        self.assertEqual("аид rp", normalized)

    def test_character_requires_explicit_adult_confirmation(self) -> None:
        with self.assertRaisesRegex(ValueError, "совершеннолетия"):
            validate_character_draft(
                RoleplayCharacterDraft(
                    name="Персонаж",
                    adult_confirmed=False,
                )
            )

    def test_character_sections_are_cleaned_without_archive_fields(self) -> None:
        draft = validate_character_draft(
            RoleplayCharacterDraft(
                name="  Аид  ",
                adult_confirmed=True,
                appearance={" eyes ": " золотые "},
                personality={"traits": [" спокойный ", "упрямый"]},
                canonical_facts=(" бессмертен ", "бессмертен"),
            )
        )
        self.assertEqual("Аид", draft.name)
        self.assertEqual({"eyes": "золотые"}, draft.appearance)
        self.assertEqual(("бессмертен",), draft.canonical_facts)
        self.assertFalse(hasattr(draft, "archive_topic_url"))
        self.assertFalse(hasattr(draft, "media_count"))

    def test_context_budget_trims_old_messages_and_preserves_user_input(self) -> None:
        now = datetime.now(UTC)
        history = tuple(
            RoleplayMessage(
                id=index,
                session_id=1,
                sequence_no=index,
                role="assistant" if index % 2 == 0 else "user",
                speaker_key=None,
                content=("длинная реплика " * 80) + str(index),
                token_count=None,
                created_at=now,
            )
            for index in range(1, 15)
        )
        result = build_roleplay_context(
            characters=(_character(),),
            scenario="Встреча в тронном зале.",
            world_lore="Мифологический мир.",
            summary="Персонажи уже знакомы.",
            scene_state={"location": "тронный зал"},
            memories=(),
            recent_messages=history,
            user_message="Я подхожу ближе.",
            budget=RoleplayContextBudget(
                num_ctx=4096,
                max_output_tokens=600,
                recent_message_limit=12,
                summary_trigger_tokens=2800,
            ),
        )
        self.assertEqual("system", result.messages[0]["role"])
        self.assertEqual("Я подхожу ближе.", result.messages[-1]["content"])
        self.assertGreater(result.trimmed_message_count, 0)
        self.assertLessEqual(result.estimated_input_tokens, 4096)

    def test_ollama_body_uses_roleplay_context_and_sampling(self) -> None:
        client = OllamaRoleplayClient(
            base_url="http://127.0.0.1:11434",
            model="velvet-rp",
        )
        options = RoleplayGenerationOptions(
            num_ctx=8192,
            max_output_tokens=900,
            temperature=0.9,
            top_p=0.92,
            min_p=0.05,
            repeat_penalty=1.08,
        )
        body = client.request_body(
            [
                {"role": "system", "content": "Оставайся в роли."},
                {"role": "user", "content": "Начинаем."},
            ],
            options,
        )
        self.assertFalse(body["stream"])
        self.assertFalse(body["think"])
        self.assertEqual(8192, body["options"]["num_ctx"])
        self.assertEqual(900, body["options"]["num_predict"])
        self.assertEqual("velvet-rp", body["model"])

    def test_roleplay_settings_are_independent_from_ai_vision(self) -> None:
        env = {
            "RP_ENABLED": "true",
            "RP_PROVIDER": "ollama",
            "RP_BASE_URL": "http://127.0.0.1:11434",
            "RP_MODEL": "velvet-rp",
            "RP_NUM_CTX": "8192",
            "RP_MAX_OUTPUT_TOKENS": "900",
            "RP_TEMPERATURE": "0.85",
            "RP_TOP_P": "0.9",
            "RP_MIN_P": "0.04",
            "RP_REPEAT_PENALTY": "1.1",
            "RP_KEEP_ALIVE": "20m",
            "RP_SUMMARY_TRIGGER_TOKENS": "5600",
            "RP_RECENT_MESSAGE_LIMIT": "18",
            "RP_TIMEOUT_SECONDS": "700",
            "AI_VISION_MODEL": "must-not-be-used",
        }
        with patch.dict(os.environ, env, clear=True):
            settings = load_roleplay_settings()
        self.assertTrue(settings.enabled)
        self.assertEqual("velvet-rp", settings.model)
        self.assertEqual(8192, settings.num_ctx)
        self.assertEqual(700, settings.timeout_seconds)

    def test_migration_is_isolated_from_archive_tables(self) -> None:
        sql = (ROOT / "migrations/915_roleplay_foundation.sql").read_text(
            encoding="utf-8"
        )
        for table in (
            "rp_characters",
            "rp_sessions",
            "rp_session_characters",
            "rp_messages",
            "rp_memories",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", sql)
        lowered = sql.casefold()
        self.assertNotIn("references characters", lowered)
        self.assertNotIn("character_media", lowered)
        self.assertNotIn("archive_", lowered)


if __name__ == "__main__":
    unittest.main()
