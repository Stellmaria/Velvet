from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER_ENV = ROOT / ".env.server.example"
LOCAL_ENV = ROOT / ".env.vision-local.example"
COMPOSE = ROOT / "docker-compose.server.yml"
RUNBOOK = ROOT / "docs" / "LOCAL_VISION_RUNBOOK.md"
AI_VISION_DOC = ROOT / "docs" / "AI_VISION.md"

MODEL = "qwen3.5:9b"
DIGEST_PREFIX = "6488c96fa5fa"
LEGACY_DEFAULT = "qwen3-vl:8b-instruct-q4_K_M"


def _env_value(text: str, name: str) -> str:
    match = re.search(rf"(?m)^{re.escape(name)}=(.*)$", text)
    if match is None:
        raise AssertionError(f"Missing {name}")
    return match.group(1).strip()


class VLLocalMainPinContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server_env = SERVER_ENV.read_text(encoding="utf-8")
        cls.local_env = LOCAL_ENV.read_text(encoding="utf-8")
        cls.compose = COMPOSE.read_text(encoding="utf-8")
        cls.runbook = RUNBOOK.read_text(encoding="utf-8")
        cls.ai_vision_doc = AI_VISION_DOC.read_text(encoding="utf-8")

    def test_env_examples_pin_canonical_local_main(self) -> None:
        for name, text in (
            ("server", self.server_env),
            ("local", self.local_env),
        ):
            with self.subTest(surface=name):
                self.assertEqual(MODEL, _env_value(text, "AI_VISION_MODEL"))
                self.assertEqual(MODEL, _env_value(text, "AI_VISION_FLASH_MODEL"))
                self.assertEqual(MODEL, _env_value(text, "VISION_MODEL"))
                self.assertEqual(
                    DIGEST_PREFIX,
                    _env_value(text, "VISION_MODEL_EXPECTED_DIGEST"),
                )
                self.assertEqual("false", _env_value(text, "AI_QUALITY_ENABLED"))
                self.assertEqual(
                    "false",
                    _env_value(text, "AI_VISION_CLOUD_PRO_ENABLED"),
                )
                self.assertEqual(
                    "false",
                    _env_value(text, "AI_VISION_LOCAL_UNCENSORED_ENABLED"),
                )

    def test_compose_fallbacks_are_fail_closed_to_same_identity(self) -> None:
        self.assertEqual(3, self.compose.count(f"${{VISION_MODEL:-{MODEL}}}"))
        self.assertEqual(
            3,
            self.compose.count(
                f"${{VISION_MODEL_EXPECTED_DIGEST:-{DIGEST_PREFIX}}}"
            ),
        )
        self.assertNotIn(LEGACY_DEFAULT, self.compose)

    def test_canonical_docs_do_not_reintroduce_legacy_default(self) -> None:
        for path, text in (
            (RUNBOOK, self.runbook),
            (AI_VISION_DOC, self.ai_vision_doc),
        ):
            with self.subTest(path=path.name):
                self.assertIn(MODEL, text)
                self.assertIn(DIGEST_PREFIX, text)
                self.assertNotIn(LEGACY_DEFAULT, text)


if __name__ == "__main__":
    unittest.main()
