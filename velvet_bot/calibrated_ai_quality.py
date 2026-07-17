from __future__ import annotations

import asyncio
import logging
from typing import Any

from velvet_bot.ai_quality import AIQualityService
from velvet_bot.ai_vision import VisionAnalysisError, VisionProviderUnavailable
from velvet_bot.quality_calibration import (
    CalibrationProfile,
    QualityCalibrationRepository,
    recommended_decision,
)

logger = logging.getLogger(__name__)


def apply_calibration_to_report(
    report: dict[str, Any],
    profile: CalibrationProfile,
) -> dict[str, Any]:
    calibrated = dict(report)
    raw_verdict = str(report.get("verdict") or "review")
    score = int(report.get("quality_score") or 0)
    confidence = int(report.get("confidence") or 0)
    recommendation = recommended_decision(
        verdict=raw_verdict,
        quality_score=score,
        confidence=confidence,
        profile=profile,
    )

    calibrated_verdict = raw_verdict
    if profile.active:
        if recommendation == "accepted" and raw_verdict == "review":
            calibrated_verdict = "ready"
        elif recommendation == "fix_required" and raw_verdict == "review":
            calibrated_verdict = "critical"
        elif score <= profile.fix_max_score and raw_verdict == "ready":
            # A low-scoring clean verdict is suspicious, but the model did not provide
            # evidence for a critical defect. Route it to manual review instead.
            calibrated_verdict = "review"
        elif confidence < profile.min_confidence and raw_verdict == "ready":
            calibrated_verdict = "review"

    calibrated["verdict"] = calibrated_verdict
    calibrated["calibration"] = {
        "active": profile.active,
        "sample_count": profile.sample_count,
        "raw_verdict": raw_verdict,
        "calibrated_verdict": calibrated_verdict,
        "recommendation": recommendation,
        "ready_min_score": profile.ready_min_score,
        "fix_max_score": profile.fix_max_score,
        "min_confidence": profile.min_confidence,
        "usefulness_rate": profile.usefulness_rate,
        "false_alarm_rate": profile.false_alarm_rate,
        "missed_problem_rate": profile.missed_problem_rate,
    }
    return calibrated


class CalibratedAIQualityService(AIQualityService):
    def __init__(self, *args, calibration_repository: QualityCalibrationRepository, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._calibration_repository = calibration_repository

    async def process_once(self) -> int:
        if not await self._provider_available():
            return 0
        targets = await self._repository.claim_targets(
            provider=self._client.provider,
            model=self._client.model,
            max_attempts=self._max_attempts,
            limit=1,
        )
        if not targets:
            return 0

        profile = await self._calibration_repository.profile(
            provider=self._client.provider,
            model=self._client.model,
        )
        processed = 0
        for target in targets:
            try:
                source = await self._download_target(target)
                raw_report = await self._client.analyze(source)
                report = apply_calibration_to_report(raw_report, profile)
                await self._repository.mark_ready(target.media_id, report)
                processed += 1
                logger.info(
                    "Calibrated AI quality report ready media_id=%s raw=%s calibrated=%s "
                    "score=%s samples=%s",
                    target.media_id,
                    raw_report.get("verdict"),
                    report.get("verdict"),
                    report.get("quality_score"),
                    profile.sample_count,
                )
            except asyncio.CancelledError:
                raise
            except VisionProviderUnavailable as error:
                self._healthy = False
                await self._repository.mark_error(
                    target.media_id,
                    error,
                    max_attempts=self._max_attempts,
                )
                break
            except Exception as error:
                logger.warning(
                    "Calibrated AI quality analysis failed media_id=%s: %s",
                    target.media_id,
                    error,
                )
                permanent = isinstance(error, VisionAnalysisError) and (
                    "прочитать как изображение" in str(error)
                    or "file is too big" in str(error).casefold()
                )
                await self._repository.mark_error(
                    target.media_id,
                    error,
                    max_attempts=self._max_attempts,
                    permanent=permanent,
                )
        return processed


__all__ = ("CalibratedAIQualityService", "apply_calibration_to_report")
