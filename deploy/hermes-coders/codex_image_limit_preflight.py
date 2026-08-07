#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Mapping

import byesu_image_fallback as fallback
import byesu_image_routing_policy as routing
import codex_image_runner as image_runner
from codex_availability import CodexAvailabilityError, classify_rate_limits
from codex_first_runner import provider_fallback_reason

_INSTALLED = False
_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


def codex_limit_exhausted(
    snapshot: object,
    *,
    now_epoch: float | None = None,
) -> bool:
    """Compatibility helper for tests and diagnostics, not a request preflight."""
    try:
        available, _ = classify_rate_limits(snapshot, now_epoch=now_epoch)
    except CodexAvailabilityError:
        return False
    return not available


def _snapshot_from_state(state: Mapping[str, object]) -> dict[str, object]:
    snapshot = state.get("rate_limits")
    return dict(snapshot) if isinstance(snapshot, Mapping) else {}


def _rewrite_gate_result(
    manager: Any,
    run_id: str,
    state: Mapping[str, object],
) -> None:
    record = manager.store.read(run_id)
    last_event = record.get("last_event")
    event = dict(last_event) if isinstance(last_event, Mapping) else {}
    event.update(
        {
            "route_reason": "codex_availability_gate",
            "availability_reason": state.get("reason"),
            "codex_generation_skipped": True,
        }
    )
    manager.store.update(
        run_id,
        requested_route="codex_subscription",
        actual_route="byesu_media",
        route_reason="codex_availability_gate",
        fallback_reason="subscription_limit",
        availability_reason=state.get("reason"),
        codex_generation_skipped=True,
        rate_limits_before=_snapshot_from_state(state),
        last_event=event,
    )


def _fail_gate_route(
    manager: Any,
    run_id: str,
    state: Mapping[str, object],
    error: Exception,
) -> None:
    try:
        record = manager.store.read(run_id)
    except Exception:
        return
    if str(record.get("status") or "") in _TERMINAL_STATUSES:
        return
    manager.store.update(
        run_id,
        status="failed",
        finished_at=fallback.utc_now(),
        requested_route="codex_subscription",
        actual_route=None,
        route_reason="codex_availability_gate",
        fallback_reason="subscription_limit",
        availability_reason=state.get("reason"),
        codex_generation_skipped=True,
        rate_limits_before=_snapshot_from_state(state),
        error=fallback.redact_text(str(error).strip())[-8_000:]
        or type(error).__name__,
        last_event={
            "type": "codex_availability_gate_failed",
            "availability_reason": state.get("reason"),
            "error_type": type(error).__name__,
            "codex_generation_skipped": True,
        },
    )


def _run_gate_byesu(
    manager: Any,
    run_id: str,
    prompt: str,
    state: Mapping[str, object],
) -> None:
    staged: Path | None = None
    with manager._isolation_lock:
        try:
            record = manager.store.read(run_id)
            if record.get("stop_requested"):
                manager.store.update(
                    run_id,
                    status="cancelled",
                    finished_at=fallback.utc_now(),
                    rate_limits_before=_snapshot_from_state(state),
                    last_event={"type": "image_cancelled_before_start"},
                )
                return
            staged = fallback._stage_references(manager, run_id)
            manager.store.update(
                run_id,
                status="running",
                started_at=fallback.utc_now(),
                requested_route="codex_subscription",
                actual_route="byesu_media",
                route_reason="codex_availability_gate",
                fallback_reason="subscription_limit",
                availability_reason=state.get("reason"),
                codex_generation_skipped=True,
                rate_limits_before=_snapshot_from_state(state),
                last_event={
                    "type": "codex_availability_gate_byesu",
                    "availability_reason": state.get("reason"),
                    "codex_generation_skipped": True,
                },
            )
            routing._run_byesu(manager, run_id, prompt, staged, direct=True)
            _rewrite_gate_result(manager, run_id, state)
        except Exception as error:
            _fail_gate_route(manager, run_id, state, error)
        finally:
            if staged is not None:
                shutil.rmtree(staged, ignore_errors=True)
            manager._cleanup_image_inputs(run_id)


def _record_reports_subscription_limit(record: Mapping[str, object]) -> bool:
    if str(record.get("fallback_reason") or "") == "subscription_limit":
        return True
    combined = "\n".join(
        str(record.get(name) or "")
        for name in ("error", "output")
    )
    return provider_fallback_reason(combined) == "subscription_limit"


def install_codex_image_limit_preflight() -> None:
    """Route GPT Image 2 exclusively from the shared dynamic availability flag."""
    global _INSTALLED
    if _INSTALLED:
        return

    original = image_runner.CodexImageSupport._execute_image

    def execute_with_availability_gate(
        self: Any,
        run_id: str,
        prompt: str,
    ) -> None:
        gate = getattr(self, "codex_availability", None)
        if gate is None:
            original(self, run_id, prompt)
            return
        record = self.store.read(run_id)
        resolution = str(record.get("resolution") or "1K")
        if not routing.uses_codex_primary(resolution):
            original(self, run_id, prompt)
            return

        state = gate.status()
        if state.get("codex_available") is not True:
            if fallback._enabled():
                _run_gate_byesu(self, run_id, prompt, state)
            else:
                _fail_gate_route(
                    self,
                    run_id,
                    state,
                    RuntimeError(
                        "Codex dynamic availability flag is false and GPT Image 2 fallback is disabled"
                    ),
                )
                self._cleanup_image_inputs(run_id)
            return

        original(self, run_id, prompt)
        finished = self.store.read(run_id)
        if _record_reports_subscription_limit(finished):
            gate.note_subscription_failure("subscription_limit")

    image_runner.CodexImageSupport._execute_image = execute_with_availability_gate
    _INSTALLED = True


__all__ = (
    "codex_limit_exhausted",
    "install_codex_image_limit_preflight",
)
