#!/usr/bin/env python3
from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Any, Mapping

import byesu_image_fallback as fallback
import byesu_image_routing_policy as routing
import codex_image_runner as image_runner
from codex_runner import read_codex_subscription_rate_limits

_INSTALLED = False
_NOT_REACHED_VALUES = frozenset(
    {"", "none", "null", "false", "not_reached", "not-reached"}
)


def _enabled() -> bool:
    return os.environ.get(
        "CODEX_IMAGE_LIMIT_PREFLIGHT_ENABLED", "true"
    ).strip().casefold() in {"1", "true", "yes", "on", "да"}


def _timeout_seconds() -> int:
    raw = os.environ.get("CODEX_IMAGE_LIMIT_PREFLIGHT_TIMEOUT_SECONDS", "3")
    try:
        value = int(raw)
    except ValueError:
        value = 3
    return max(3, min(value, 10))


def _window_exhausted(value: object, *, now_epoch: float) -> bool:
    if not isinstance(value, Mapping):
        return False
    try:
        used_percent = float(value.get("used_percent"))
    except (TypeError, ValueError):
        return False
    if used_percent < 100:
        return False
    resets_at = value.get("resets_at")
    if resets_at is None:
        return True
    try:
        reset_epoch = float(resets_at)
    except (TypeError, ValueError):
        return True
    return reset_epoch > now_epoch


def codex_limit_exhausted(
    snapshot: object,
    *,
    now_epoch: float | None = None,
) -> bool:
    """Return true only for an explicit, currently active subscription limit."""
    if not isinstance(snapshot, Mapping):
        return False
    reached_type = str(
        snapshot.get("rate_limit_reached_type") or ""
    ).strip().casefold()
    if reached_type not in _NOT_REACHED_VALUES:
        return True
    current = time.time() if now_epoch is None else now_epoch
    return any(
        _window_exhausted(snapshot.get(name), now_epoch=current)
        for name in ("primary", "secondary")
    )


def _fresh_snapshot(manager: Any) -> dict[str, Any] | None:
    try:
        result = read_codex_subscription_rate_limits(
            manager.codex_bin,
            manager.codex_home,
            timeout_seconds=_timeout_seconds(),
        )
    except Exception:
        return None
    return result if isinstance(result, dict) else None


def _rewrite_preflight_result(
    manager: Any,
    run_id: str,
    snapshot: Mapping[str, object],
) -> None:
    record = manager.store.read(run_id)
    last_event = record.get("last_event")
    event = dict(last_event) if isinstance(last_event, Mapping) else {}
    event.update(
        {
            "route_reason": "codex_limit_preflight",
            "codex_generation_skipped": True,
        }
    )
    manager.store.update(
        run_id,
        requested_route="codex_subscription",
        actual_route="byesu_media",
        route_reason="codex_limit_preflight",
        codex_generation_skipped=True,
        rate_limits_before=dict(snapshot),
        last_event=event,
    )


def _run_preflight_byesu(
    manager: Any,
    run_id: str,
    prompt: str,
    snapshot: Mapping[str, object],
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
                    rate_limits_before=dict(snapshot),
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
                route_reason="codex_limit_preflight",
                codex_generation_skipped=True,
                rate_limits_before=dict(snapshot),
                last_event={
                    "type": "codex_limit_preflight_exhausted",
                    "codex_generation_skipped": True,
                },
            )
            routing._run_byesu(manager, run_id, prompt, staged, direct=True)
            _rewrite_preflight_result(manager, run_id, snapshot)
        finally:
            if staged is not None:
                shutil.rmtree(staged, ignore_errors=True)
            manager._cleanup_image_inputs(run_id)


def install_codex_image_limit_preflight() -> None:
    """Skip a doomed Codex 1K launch when the live limit is explicitly exhausted."""
    global _INSTALLED
    if _INSTALLED:
        return

    original = image_runner.CodexImageSupport._execute_image

    def execute_with_limit_preflight(
        self: Any,
        run_id: str,
        prompt: str,
    ) -> None:
        if not fallback._enabled() or not _enabled():
            original(self, run_id, prompt)
            return
        record = self.store.read(run_id)
        resolution = str(record.get("resolution") or "1K")
        if not routing.uses_codex_primary(resolution):
            original(self, run_id, prompt)
            return
        snapshot = _fresh_snapshot(self)
        if snapshot is None or not codex_limit_exhausted(snapshot):
            original(self, run_id, prompt)
            return
        _run_preflight_byesu(self, run_id, prompt, snapshot)

    image_runner.CodexImageSupport._execute_image = execute_with_limit_preflight
    _INSTALLED = True


__all__ = (
    "codex_limit_exhausted",
    "install_codex_image_limit_preflight",
)
