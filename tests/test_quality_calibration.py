from __future__ import annotations

import unittest

from velvet_bot.calibrated_ai_quality import apply_calibration_to_report
from velvet_bot.quality_calibration import (
    CalibrationProfile,
    FeedbackSample,
    build_calibration_profile,
    classify_feedback,
    recommended_decision,
)


def _sample(
    verdict: str,
    score: int,
    confidence: int,
    decision: str,
) -> FeedbackSample:
    return FeedbackSample(
        predicted_verdict=verdict,
        quality_score=score,
        confidence=confidence,
        owner_decision=decision,
        outcome=classify_feedback(verdict, decision),
    )


class FeedbackClassificationTests(unittest.TestCase):
    def test_classifies_false_alarm(self) -> None:
        self.assertEqual(classify_feedback("critical", "accepted"), "false_alarm")

    def test_classifies_missed_problem(self) -> None:
        self.assertEqual(
            classify_feedback("ready", "fix_required"),
            "missed_problem",
        )

    def test_classifies_useful_warning(self) -> None:
        self.assertEqual(
            classify_feedback("review", "fix_required"),
            "useful_warning",
        )


class CalibrationProfileTests(unittest.TestCase):
    def test_profile_waits_for_balanced_sample(self) -> None:
        samples = [_sample("ready", 92, 90, "accepted") for _ in range(12)]

        profile = build_calibration_profile(samples)

        self.assertFalse(profile.active)
        self.assertEqual(profile.accepted_count, 12)
        self.assertEqual(profile.fix_required_count, 0)

    def test_profile_activates_after_balanced_owner_feedback(self) -> None:
        samples = [
            *[_sample("ready", score, 88, "accepted") for score in (84, 87, 90, 92, 94, 96)],
            *[
                _sample("critical", score, 86, "fix_required")
                for score in (35, 42, 48, 53, 58, 62)
            ],
        ]

        profile = build_calibration_profile(samples)

        self.assertTrue(profile.active)
        self.assertEqual(profile.sample_count, 12)
        self.assertGreater(profile.ready_min_score, profile.fix_max_score)
        self.assertGreaterEqual(profile.min_confidence, 35)

    def test_profile_keeps_manual_review_band_for_overlapping_scores(self) -> None:
        samples = [
            *[_sample("ready", score, 80, "accepted") for score in (68, 70, 72, 74, 76, 78)],
            *[
                _sample("review", score, 80, "fix_required")
                for score in (70, 72, 74, 76, 78, 80)
            ],
        ]

        profile = build_calibration_profile(samples)

        self.assertTrue(profile.active)
        self.assertGreaterEqual(profile.ready_min_score - profile.fix_max_score, 8)


class CalibratedRoutingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = CalibrationProfile(
            sample_count=20,
            useful_count=16,
            false_alarm_count=2,
            missed_problem_count=2,
            uncertain_count=0,
            accepted_count=10,
            fix_required_count=10,
            usefulness_rate=80,
            false_alarm_rate=10,
            missed_problem_rate=10,
            ready_min_score=84,
            fix_max_score=58,
            min_confidence=55,
            active=True,
        )

    def test_high_score_review_is_routed_to_ready(self) -> None:
        report = {
            "verdict": "review",
            "quality_score": 93,
            "confidence": 90,
        }

        calibrated = apply_calibration_to_report(report, self.profile)

        self.assertEqual(calibrated["verdict"], "ready")
        self.assertEqual(calibrated["calibration"]["raw_verdict"], "review")
        self.assertEqual(calibrated["calibration"]["recommendation"], "accepted")

    def test_low_score_review_is_routed_to_critical(self) -> None:
        report = {
            "verdict": "review",
            "quality_score": 44,
            "confidence": 90,
        }

        calibrated = apply_calibration_to_report(report, self.profile)

        self.assertEqual(calibrated["verdict"], "critical")
        self.assertEqual(
            calibrated["calibration"]["recommendation"],
            "fix_required",
        )

    def test_low_confidence_ready_is_sent_to_manual_review(self) -> None:
        report = {
            "verdict": "ready",
            "quality_score": 95,
            "confidence": 30,
        }

        calibrated = apply_calibration_to_report(report, self.profile)

        self.assertEqual(calibrated["verdict"], "review")
        self.assertEqual(
            calibrated["calibration"]["recommendation"],
            "manual_review",
        )

    def test_inactive_profile_does_not_change_verdict(self) -> None:
        inactive = CalibrationProfile(
            sample_count=5,
            useful_count=4,
            false_alarm_count=1,
            missed_problem_count=0,
            uncertain_count=0,
            accepted_count=4,
            fix_required_count=1,
            usefulness_rate=80,
            false_alarm_rate=20,
            missed_problem_rate=0,
            ready_min_score=82,
            fix_max_score=62,
            min_confidence=50,
            active=False,
        )
        report = {
            "verdict": "review",
            "quality_score": 95,
            "confidence": 95,
        }

        calibrated = apply_calibration_to_report(report, inactive)

        self.assertEqual(calibrated["verdict"], "review")
        self.assertFalse(calibrated["calibration"]["active"])

    def test_recommended_decision_respects_critical_evidence(self) -> None:
        decision = recommended_decision(
            verdict="critical",
            quality_score=95,
            confidence=95,
            profile=self.profile,
        )

        self.assertEqual(decision, "manual_review")


if __name__ == "__main__":
    unittest.main()
