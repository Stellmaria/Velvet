from __future__ import annotations

import logging
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from velvet_bot.ai_vision import VisionAnalysisError, VisionAnalysisTarget
from velvet_bot.calibrated_ai_quality import CalibratedAIQualityService
from velvet_bot.quality_calibration import CalibrationProfile


_PROFILE = CalibrationProfile(
    sample_count=0,
    useful_count=0,
    false_alarm_count=0,
    missed_problem_count=0,
    uncertain_count=0,
    accepted_count=0,
    fix_required_count=0,
    usefulness_rate=0,
    false_alarm_rate=0,
    missed_problem_rate=0,
    ready_min_score=80,
    fix_max_score=45,
    min_confidence=60,
    active=False,
)


class CalibratedAITerminalSkipLoggingTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def _service(error: BaseException):
        target = VisionAnalysisTarget(
            media_id=3366,
            telegram_file_id="large-file",
            preview_file_id=None,
            mime_type="image/jpeg",
        )
        repository = SimpleNamespace(
            claim_targets=AsyncMock(return_value=(target,)),
            mark_error=AsyncMock(),
            mark_ready=AsyncMock(),
        )
        client = SimpleNamespace(
            provider="ollama",
            model="qwen3-vl:8b",
            analyze=AsyncMock(),
        )
        calibration_repository = SimpleNamespace(
            profile=AsyncMock(return_value=_PROFILE),
        )
        service = object.__new__(CalibratedAIQualityService)
        service._repository = repository
        service._client = client
        service._calibration_repository = calibration_repository
        service._max_attempts = 3
        service._provider_available = AsyncMock(return_value=True)
        service._download_target = AsyncMock(side_effect=error)
        return service, repository

    async def test_oversized_terminal_skip_is_logged_as_info(self) -> None:
        error = VisionAnalysisError(
            "Крупное изображение недоступно для AI-анализа media_key=m3366: "
            "file is too big, а Telegram не предоставил доступную миниатюру. "
            "Повтор автоматически не требуется."
        )
        service, repository = self._service(error)

        with self.assertLogs("velvet_bot.calibrated_ai_quality", level="INFO") as captured:
            processed = await service.process_once()

        self.assertEqual(0, processed)
        self.assertEqual(logging.INFO, captured.records[0].levelno)
        repository.mark_error.assert_awaited_once_with(
            3366,
            error,
            max_attempts=3,
            permanent=True,
        )

    async def test_unrelated_failure_remains_warning_and_retryable(self) -> None:
        error = RuntimeError("temporary filesystem failure")
        service, repository = self._service(error)

        with self.assertLogs("velvet_bot.calibrated_ai_quality", level="WARNING") as captured:
            processed = await service.process_once()

        self.assertEqual(0, processed)
        self.assertEqual(logging.WARNING, captured.records[0].levelno)
        repository.mark_error.assert_awaited_once_with(
            3366,
            error,
            max_attempts=3,
            permanent=False,
        )


if __name__ == "__main__":
    unittest.main()
