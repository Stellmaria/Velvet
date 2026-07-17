from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Sequence

from velvet_bot.database import Database

_OUTCOMES = (
    "correct_clean",
    "correct_fix",
    "useful_warning",
    "false_alarm",
    "missed_problem",
    "uncertain",
)
_USEFUL_OUTCOMES = ("correct_clean", "correct_fix", "useful_warning")
_ERROR_OUTCOMES = ("false_alarm", "missed_problem")


@dataclass(frozen=True, slots=True)
class FeedbackSample:
    predicted_verdict: str
    quality_score: int
    confidence: int
    owner_decision: str
    outcome: str


@dataclass(frozen=True, slots=True)
class CalibrationProfile:
    sample_count: int
    useful_count: int
    false_alarm_count: int
    missed_problem_count: int
    uncertain_count: int
    accepted_count: int
    fix_required_count: int
    usefulness_rate: int
    false_alarm_rate: int
    missed_problem_rate: int
    ready_min_score: int
    fix_max_score: int
    min_confidence: int
    active: bool

    @property
    def collecting_count(self) -> int:
        return max(0, 12 - self.sample_count)


@dataclass(frozen=True, slots=True)
class CalibrationCase:
    feedback_id: int
    media_id: int
    file_name: str
    predicted_verdict: str
    quality_score: int
    confidence: int
    owner_decision: str
    outcome: str
    report: dict[str, Any] | None
    decided_by: int | None
    decided_at: datetime


@dataclass(frozen=True, slots=True)
class CalibrationCasePage:
    items: tuple[CalibrationCase, ...]
    page: int
    page_size: int
    total_items: int

    @property
    def total_pages(self) -> int:
        return max(1, (self.total_items + self.page_size - 1) // self.page_size)


def clamp_score(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 0
    return max(0, min(parsed, 100))


def classify_feedback(predicted_verdict: str, owner_decision: str) -> str:
    verdict = str(predicted_verdict or "").strip().casefold()
    decision = str(owner_decision or "").strip().casefold()
    if verdict == "ready" and decision == "accepted":
        return "correct_clean"
    if verdict == "critical" and decision == "fix_required":
        return "correct_fix"
    if verdict == "review" and decision == "fix_required":
        return "useful_warning"
    if verdict in {"review", "critical"} and decision == "accepted":
        return "false_alarm"
    if verdict == "ready" and decision == "fix_required":
        return "missed_problem"
    return "uncertain"


def _percentile(values: Sequence[int], fraction: float, default: int) -> int:
    if not values:
        return default
    ordered = sorted(clamp_score(value) for value in values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(float(fraction), 1.0)) * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return round(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def build_calibration_profile(samples: Iterable[FeedbackSample]) -> CalibrationProfile:
    normalized: list[FeedbackSample] = []
    for sample in samples:
        outcome = (
            sample.outcome
            if sample.outcome in _OUTCOMES
            else classify_feedback(sample.predicted_verdict, sample.owner_decision)
        )
        normalized.append(
            FeedbackSample(
                predicted_verdict=str(sample.predicted_verdict),
                quality_score=clamp_score(sample.quality_score),
                confidence=clamp_score(sample.confidence),
                owner_decision=str(sample.owner_decision),
                outcome=outcome,
            )
        )

    sample_count = len(normalized)
    accepted = [sample for sample in normalized if sample.owner_decision == "accepted"]
    fix_required = [
        sample for sample in normalized if sample.owner_decision == "fix_required"
    ]
    useful_count = sum(sample.outcome in _USEFUL_OUTCOMES for sample in normalized)
    false_alarm_count = sum(sample.outcome == "false_alarm" for sample in normalized)
    missed_problem_count = sum(
        sample.outcome == "missed_problem" for sample in normalized
    )
    uncertain_count = sum(sample.outcome == "uncertain" for sample in normalized)
    decisive_count = max(1, sample_count - uncertain_count)

    ready_min_score = max(
        65,
        min(
            _percentile(
                [sample.quality_score for sample in accepted],
                0.20,
                82,
            ),
            95,
        ),
    )
    fix_max_score = max(
        35,
        min(
            _percentile(
                [sample.quality_score for sample in fix_required],
                0.80,
                62,
            ),
            85,
        ),
    )
    if fix_max_score >= ready_min_score - 7:
        center = round((fix_max_score + ready_min_score) / 2)
        fix_max_score = max(35, min(center - 4, 82))
        ready_min_score = max(68, min(center + 4, 95))

    min_confidence = max(
        35,
        min(
            _percentile(
                [sample.confidence for sample in normalized],
                0.25,
                50,
            ),
            75,
        ),
    )
    active = sample_count >= 12 and len(accepted) >= 3 and len(fix_required) >= 3

    return CalibrationProfile(
        sample_count=sample_count,
        useful_count=useful_count,
        false_alarm_count=false_alarm_count,
        missed_problem_count=missed_problem_count,
        uncertain_count=uncertain_count,
        accepted_count=len(accepted),
        fix_required_count=len(fix_required),
        usefulness_rate=round(useful_count * 100 / decisive_count),
        false_alarm_rate=round(false_alarm_count * 100 / decisive_count),
        missed_problem_rate=round(missed_problem_count * 100 / decisive_count),
        ready_min_score=ready_min_score,
        fix_max_score=fix_max_score,
        min_confidence=min_confidence,
        active=active,
    )


def recommended_decision(
    *,
    verdict: str,
    quality_score: int,
    confidence: int,
    profile: CalibrationProfile,
) -> str:
    if not profile.active or clamp_score(confidence) < profile.min_confidence:
        return "manual_review"
    score = clamp_score(quality_score)
    normalized_verdict = str(verdict or "").strip().casefold()
    if score >= profile.ready_min_score and normalized_verdict != "critical":
        return "accepted"
    if score <= profile.fix_max_score and normalized_verdict != "ready":
        return "fix_required"
    return "manual_review"


def _decode_report(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


class QualityCalibrationRepository:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def profile(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        limit: int = 1000,
    ) -> CalibrationProfile:
        safe_limit = max(20, min(int(limit), 5000))
        async with self._database._require_pool().acquire() as connection:
            rows = await connection.fetch(
                """
                SELECT predicted_verdict, quality_score, confidence,
                       owner_decision, outcome
                FROM qwen_quality_feedback
                WHERE ($1::VARCHAR IS NULL OR provider = $1::VARCHAR)
                  AND ($2::VARCHAR IS NULL OR model = $2::VARCHAR)
                ORDER BY created_at DESC, id DESC
                LIMIT $3::INTEGER
                """,
                provider,
                model,
                safe_limit,
            )
        return build_calibration_profile(
            FeedbackSample(
                predicted_verdict=str(row["predicted_verdict"]),
                quality_score=int(row["quality_score"]),
                confidence=int(row["confidence"]),
                owner_decision=str(row["owner_decision"]),
                outcome=str(row["outcome"]),
            )
            for row in rows
        )

    @staticmethod
    def _section_outcomes(section: str) -> tuple[str, ...] | None:
        sections: dict[str, tuple[str, ...] | None] = {
            "all": None,
            "errors": _ERROR_OUTCOMES,
            "useful": _USEFUL_OUTCOMES,
            "uncertain": ("uncertain",),
            "false_alarm": ("false_alarm",),
            "missed_problem": ("missed_problem",),
        }
        if section not in sections:
            raise ValueError("Неизвестный раздел калибровки Qwen.")
        return sections[section]

    async def list_cases(
        self,
        section: str,
        *,
        provider: str | None,
        model: str | None,
        page: int = 0,
        page_size: int = 6,
    ) -> CalibrationCasePage:
        outcomes = self._section_outcomes(section)
        safe_size = max(1, min(int(page_size), 10))
        outcome_values = list(outcomes) if outcomes is not None else None
        async with self._database._require_pool().acquire() as connection:
            total = int(
                await connection.fetchval(
                    """
                    SELECT COUNT(*)
                    FROM qwen_quality_feedback AS feedback
                    WHERE ($1::VARCHAR IS NULL OR feedback.provider = $1::VARCHAR)
                      AND ($2::VARCHAR IS NULL OR feedback.model = $2::VARCHAR)
                      AND ($3::VARCHAR[] IS NULL
                           OR feedback.outcome = ANY($3::VARCHAR[]))
                    """,
                    provider,
                    model,
                    outcome_values,
                )
                or 0
            )
            total_pages = max(1, (total + safe_size - 1) // safe_size)
            safe_page = min(max(0, int(page)), total_pages - 1)
            rows = await connection.fetch(
                """
                SELECT feedback.*,
                       COALESCE(
                           media.original_file_name,
                           media.storage_file_name,
                           'media-' || media.id::TEXT
                       ) AS file_name
                FROM qwen_quality_feedback AS feedback
                JOIN media_files AS media ON media.id = feedback.media_id
                WHERE ($1::VARCHAR IS NULL OR feedback.provider = $1::VARCHAR)
                  AND ($2::VARCHAR IS NULL OR feedback.model = $2::VARCHAR)
                  AND ($3::VARCHAR[] IS NULL
                       OR feedback.outcome = ANY($3::VARCHAR[]))
                ORDER BY feedback.created_at DESC, feedback.id DESC
                OFFSET $4::INTEGER LIMIT $5::INTEGER
                """,
                provider,
                model,
                outcome_values,
                safe_page * safe_size,
                safe_size,
            )
        return CalibrationCasePage(
            items=tuple(self._case_from_row(row) for row in rows),
            page=safe_page,
            page_size=safe_size,
            total_items=total,
        )

    async def get_case(self, feedback_id: int) -> CalibrationCase | None:
        async with self._database._require_pool().acquire() as connection:
            row = await connection.fetchrow(
                """
                SELECT feedback.*,
                       COALESCE(
                           media.original_file_name,
                           media.storage_file_name,
                           'media-' || media.id::TEXT
                       ) AS file_name
                FROM qwen_quality_feedback AS feedback
                JOIN media_files AS media ON media.id = feedback.media_id
                WHERE feedback.id = $1::BIGINT
                """,
                int(feedback_id),
            )
        return self._case_from_row(row) if row is not None else None

    @staticmethod
    def _case_from_row(row: Any) -> CalibrationCase:
        return CalibrationCase(
            feedback_id=int(row["id"]),
            media_id=int(row["media_id"]),
            file_name=str(row["file_name"]),
            predicted_verdict=str(row["predicted_verdict"]),
            quality_score=int(row["quality_score"]),
            confidence=int(row["confidence"]),
            owner_decision=str(row["owner_decision"]),
            outcome=str(row["outcome"]),
            report=_decode_report(row["report"]),
            decided_by=(
                int(row["decided_by"]) if row["decided_by"] is not None else None
            ),
            decided_at=row["decided_at"],
        )


__all__ = (
    "CalibrationCase",
    "CalibrationCasePage",
    "CalibrationProfile",
    "FeedbackSample",
    "QualityCalibrationRepository",
    "build_calibration_profile",
    "classify_feedback",
    "recommended_decision",
)
