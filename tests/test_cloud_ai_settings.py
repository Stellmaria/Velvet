from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from velvet_bot.core.config.settings import load_settings


_BASE_ENV = {
    "BOT_TOKEN": "telegram-token",
    "DATABASE_URL": "postgresql://velvet:test@localhost:5432/velvet",
    "ALLOWED_USER_IDS": "100",
}


class CloudAISettingsTests(unittest.TestCase):
    def _load(self, **values: str):
        environment = {**_BASE_ENV, **values}
        with patch.dict(os.environ, environment, clear=True), patch(
            "velvet_bot.core.config.settings.load_dotenv"
        ):
            return load_settings()

    def test_disabled_ai_defaults_to_cloud_endpoints_without_model(self) -> None:
        settings = self._load()
        self.assertFalse(settings.ai_text_enabled)
        self.assertFalse(settings.ai_vision_enabled)
        self.assertEqual(settings.ai_text_provider, "openai_compatible")
        self.assertEqual(settings.ai_vision_provider, "openai_compatible")
        self.assertEqual(settings.ai_text_base_url, "https://byesu.com/v1")
        self.assertEqual(settings.ai_vision_base_url, "https://byesu.com/v1")
        self.assertIsNone(settings.ai_text_model)
        self.assertEqual(settings.ai_vision_model, "")

    def test_shared_byesu_key_is_used_for_text_and_vision(self) -> None:
        settings = self._load(
            BYESU_API_KEY="shared-key",
            AI_TEXT_ENABLED="true",
            AI_TEXT_MODEL="roleplay-model",
            AI_VISION_ENABLED="true",
            AI_VISION_MODEL="vision-model",
        )
        self.assertEqual(settings.ai_text_api_key, "shared-key")
        self.assertEqual(settings.ai_vision_api_key, "shared-key")

    def test_enabled_cloud_text_requires_api_key(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "API_KEY"):
            self._load(
                AI_TEXT_ENABLED="true",
                AI_TEXT_MODEL="roleplay-model",
            )

    def test_enabled_cloud_vision_requires_model(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "AI_VISION_MODEL"):
            self._load(
                BYESU_API_KEY="shared-key",
                AI_VISION_ENABLED="true",
            )


if __name__ == "__main__":
    unittest.main()
