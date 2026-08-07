from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from velvet_bot.app.workers import _env_enabled
from velvet_bot.calibrated_ai_quality import CalibratedAIQualityService


ROOT = Path(__file__).resolve().parents[1]


class VLQualityWorkerGateTests(unittest.IsolatedAsyncioTestCase):
    async def test_background_quality_processing_is_fail_closed(self) -> None:
        service = object.__new__(CalibratedAIQualityService)
        service._background_enabled = False
        service._provider_available = AsyncMock(return_value=True)
        service._repository = SimpleNamespace(claim_targets=AsyncMock())

        processed = await service.process_once()

        self.assertEqual(0, processed)
        service._provider_available.assert_not_awaited()
        service._repository.claim_targets.assert_not_awaited()

    def test_quality_gate_defaults_to_disabled(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(_env_enabled("AI_QUALITY_ENABLED"))
        with patch.dict("os.environ", {"AI_QUALITY_ENABLED": "true"}, clear=True):
            self.assertTrue(_env_enabled("AI_QUALITY_ENABLED"))

    def test_quality_gate_defaults_to_disabled_in_env_examples(self) -> None:
        for relative_path in (".env.server.example", ".env.vision-local.example"):
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertIn("AI_QUALITY_ENABLED=false", source, relative_path)


if __name__ == "__main__":
    unittest.main()
