from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CODERS = ROOT / "deploy" / "hermes-coders"
if str(CODERS) not in sys.path:
    sys.path.insert(0, str(CODERS))

from codex_availability import (  # noqa: E402
    CodexAvailabilityGate,
    STATE_POLL_SECONDS,
    classify_rate_limits,
)


class FakeClock:
    def __init__(self, value: int) -> None:
        self.value = value

    def __call__(self) -> float:
        return float(self.value)


class MutableProbe:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.snapshot = snapshot
        self.calls = 0
        self.error: Exception | None = None

    def __call__(self) -> dict[str, Any]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.snapshot


class CodexAvailabilityTests(unittest.TestCase):
    def make_gate(
        self,
        probe: MutableProbe,
        clock: FakeClock,
        *,
        refresh_seconds: int = 18_000,
    ) -> tuple[tempfile.TemporaryDirectory, CodexAvailabilityGate]:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        gate = CodexAvailabilityGate(
            root=Path(directory.name),
            probe=probe,
            refresh_seconds=refresh_seconds,
            clock=clock,
        )
        return directory, gate

    def test_classification_uses_latest_blocking_reset(self) -> None:
        available, available_at = classify_rate_limits(
            {
                "rate_limit_reached_type": "secondary",
                "primary": {
                    "used_percent": 100,
                    "resets_at": 2_000,
                },
                "secondary": {
                    "used_percent": 100,
                    "resets_at": 8_000,
                },
            },
            now_epoch=1_000,
        )
        self.assertFalse(available)
        self.assertEqual(8_000, available_at)

    def test_unknown_state_starts_false(self) -> None:
        probe = MutableProbe({})
        clock = FakeClock(1_000)
        _, gate = self.make_gate(probe, clock)
        state = gate.status()
        self.assertFalse(state["codex_available"])
        self.assertEqual("unknown", state["reason"])

    def test_periodic_refresh_has_independent_five_hour_cadence(self) -> None:
        probe = MutableProbe(
            {
                "rate_limit_reached_type": None,
                "primary": {
                    "used_percent": 20,
                    "resets_at": 2_000,
                },
            }
        )
        clock = FakeClock(1_000)
        _, gate = self.make_gate(probe, clock)
        state = gate.refresh(source="startup", periodic=True)
        self.assertTrue(state["codex_available"])
        self.assertEqual(19_000, state["next_periodic_check_at"])

        clock.value = 4_000
        gate.refresh(source="operator_refresh")
        state = gate.status()
        self.assertEqual(
            19_000,
            state["next_periodic_check_at"],
            "ad-hoc refresh must not postpone the mandatory 5h check",
        )

    def test_five_hour_refresh_detects_early_weekly_reset(self) -> None:
        probe = MutableProbe(
            {
                "rate_limit_reached_type": "secondary",
                "secondary": {
                    "used_percent": 100,
                    "resets_at": 700_000,
                },
            }
        )
        clock = FakeClock(100_000)
        _, gate = self.make_gate(probe, clock)
        limited = gate.refresh(source="startup", periodic=True)
        self.assertFalse(limited["codex_available"])
        self.assertEqual(700_000, limited["codex_available_at"])

        # OpenAI restores the weekly quota early. The mandatory 5h refresh must
        # discover it even though the old resets_at is still days away.
        clock.value += 18_000
        probe.snapshot = {
            "rate_limit_reached_type": None,
            "secondary": {
                "used_percent": 40,
                "resets_at": 700_000,
            },
        }
        restored = gate.refresh(source="periodic_5h", periodic=True)
        self.assertTrue(restored["codex_available"])
        self.assertIsNone(restored["codex_available_at"])

    def test_probe_error_does_not_invent_true_from_unknown(self) -> None:
        probe = MutableProbe({})
        probe.error = RuntimeError("offline")
        clock = FakeClock(1_000)
        _, gate = self.make_gate(probe, clock)
        state = gate.refresh(source="startup", periodic=True)
        self.assertFalse(state["codex_available"])
        self.assertEqual("unknown", state["reason"])
        self.assertIn("offline", state["last_error"])
        self.assertEqual(19_000, state["next_periodic_check_at"])

    def test_explicit_execution_limit_stays_false_if_probe_disagrees(self) -> None:
        probe = MutableProbe(
            {
                "rate_limit_reached_type": None,
                "primary": {"used_percent": 15, "resets_at": 5_000},
            }
        )
        clock = FakeClock(1_000)
        _, gate = self.make_gate(probe, clock)
        gate.refresh(source="startup", periodic=True)
        self.assertTrue(gate.codex_available)

        state = gate.note_subscription_failure("subscription_limit")
        self.assertFalse(state["codex_available"])
        self.assertFalse(state["provider_available"])
        self.assertEqual("subscription_limit", state["provider_reason"])
        self.assertIn("disagreed", state["last_error"])
        self.assertEqual(
            19_000,
            state["next_periodic_check_at"],
            "execution failure must not shift the 5h periodic schedule",
        )

    def test_manual_auto_hold_clears_only_after_successful_live_probe(self) -> None:
        probe = MutableProbe(
            {
                "rate_limit_reached_type": "primary",
                "primary": {
                    "used_percent": 100,
                    "resets_at": 2_000,
                },
            }
        )
        clock = FakeClock(1_000)
        directory, gate = self.make_gate(probe, clock)
        held = gate.hold("auto")
        self.assertFalse(held["codex_available"])
        self.assertTrue(held["manual_hold"])
        self.assertEqual(2_000, held["manual_hold_until"])

        # The state is persisted and visible to a separate operator/runtime process.
        second = CodexAvailabilityGate(
            root=Path(directory.name),
            probe=probe,
            refresh_seconds=18_000,
            clock=clock,
        )
        self.assertTrue(second.status()["manual_hold"])

        clock.value = 2_001
        probe.error = RuntimeError("temporary probe error")
        still_held = gate.refresh(source="manual_hold_expiry")
        self.assertTrue(still_held["manual_hold"])
        self.assertFalse(still_held["codex_available"])

        probe.error = None
        probe.snapshot = {
            "rate_limit_reached_type": None,
            "primary": {
                "used_percent": 0,
                "resets_at": 3_000,
            },
        }
        restored = gate.refresh(source="periodic_5h", periodic=True)
        self.assertFalse(restored["manual_hold"])
        self.assertTrue(restored["codex_available"])

    def test_clear_does_live_refresh_instead_of_forcing_true(self) -> None:
        probe = MutableProbe(
            {
                "rate_limit_reached_type": None,
                "primary": {"used_percent": 10, "resets_at": 5_000},
            }
        )
        clock = FakeClock(1_000)
        _, gate = self.make_gate(probe, clock)
        gate.refresh(source="startup", periodic=True)
        gate.hold("4000")
        probe.snapshot = {
            "rate_limit_reached_type": "primary",
            "primary": {"used_percent": 100, "resets_at": 5_000},
        }
        state = gate.clear()
        self.assertFalse(state["manual_hold"])
        self.assertFalse(state["codex_available"])
        self.assertEqual(5_000, state["codex_available_at"])

    def test_background_uses_local_state_poll_without_extra_provider_cadence(self) -> None:
        self.assertEqual(60, STATE_POLL_SECONDS)
        source = (CODERS / "codex_availability.py").read_text(encoding="utf-8")
        self.assertIn("float(STATE_POLL_SECONDS)", source)
        self.assertIn("local state-file poll only", source)


if __name__ == "__main__":
    unittest.main()
