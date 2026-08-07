#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import json
import os
import tempfile
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

DEFAULT_REFRESH_SECONDS = 5 * 60 * 60
STATE_POLL_SECONDS = 60
_NOT_REACHED_VALUES = frozenset(
    {"", "none", "null", "false", "not_reached", "not-reached"}
)


class CodexAvailabilityError(RuntimeError):
    pass


def _epoch(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(float(value))
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _used_percent(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not 0 <= result <= 100:
        return None
    return result


def _window(value: object) -> Mapping[str, object] | None:
    return value if isinstance(value, Mapping) else None


def classify_rate_limits(
    snapshot: object,
    *,
    now_epoch: float | None = None,
) -> tuple[bool, int | None]:
    """Return provider availability and the next known recovery epoch."""

    if not isinstance(snapshot, Mapping):
        raise CodexAvailabilityError("Codex rate-limit snapshot имеет неверный формат")
    now = time.time() if now_epoch is None else float(now_epoch)
    reached_type = str(snapshot.get("rate_limit_reached_type") or "").strip().casefold()
    reached = reached_type not in _NOT_REACHED_VALUES
    blocking_resets: list[int] = []
    future_resets: list[int] = []
    active_hundred = False
    for name in ("primary", "secondary"):
        value = _window(snapshot.get(name))
        if value is None:
            continue
        reset = _epoch(value.get("resets_at"))
        if reset is not None and reset > now:
            future_resets.append(reset)
        used = _used_percent(value.get("used_percent"))
        if used is None or used < 100:
            continue
        if reset is None or reset > now:
            active_hundred = True
            if reset is not None:
                blocking_resets.append(reset)
    limited = reached or active_hundred
    if not limited:
        return True, None
    candidates = blocking_resets or future_resets
    return False, max(candidates) if candidates else None


def parse_until(value: str, *, now_epoch: float | None = None) -> int:
    raw = value.strip()
    if not raw:
        raise CodexAvailabilityError("Пустое время manual hold")
    current = time.time() if now_epoch is None else float(now_epoch)
    try:
        numeric = int(float(raw))
    except ValueError:
        numeric = 0
    if numeric > current:
        return numeric
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise CodexAvailabilityError(
            "--until должен быть auto, Unix epoch или ISO-8601 timestamp"
        ) from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    epoch = int(parsed.timestamp())
    if epoch <= current:
        raise CodexAvailabilityError("Manual hold должен заканчиваться в будущем")
    return epoch


class CodexAvailabilityGate:
    """Persistent dynamic gate shared by coder and GPT Image 2 routes.

    The state file is authoritative instead of an environment variable: a
    separate operator process can change it atomically and the already-running
    coder observes the new value on its next routing decision.
    """

    def __init__(
        self,
        *,
        root: Path,
        probe: Callable[[], dict[str, Any]],
        refresh_seconds: int | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.root / "codex-availability.json"
        self.lock_path = self.root / ".codex-availability.lock"
        self.probe = probe
        configured = refresh_seconds
        if configured is None:
            raw = os.environ.get(
                "CODEX_AVAILABILITY_REFRESH_SECONDS",
                str(DEFAULT_REFRESH_SECONDS),
            )
            try:
                configured = int(raw)
            except ValueError:
                configured = DEFAULT_REFRESH_SECONDS
        # Production contract is five hours. Tests may inject a shorter value.
        self.refresh_seconds = max(1, int(configured))
        self.clock = clock
        self._background_lock = threading.Lock()
        self._background_started = False
        self._wake = threading.Event()
        self._ensure_state()

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "version": 1,
            "codex_available": False,
            "codex_available_at": None,
            "provider_available": None,
            "reason": "unknown",
            "provider_reason": "unknown",
            "last_checked_at": None,
            "last_check_source": None,
            "last_periodic_check_at": None,
            "next_periodic_check_at": None,
            "manual_hold": False,
            "manual_hold_until": None,
            "rate_limits": None,
            "last_error": None,
        }

    def _lock(self, *, exclusive: bool):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        handle = self.lock_path.open("a+", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        return handle

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._default_state()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CodexAvailabilityError(
                f"Повреждён Codex availability state: {type(error).__name__}"
            ) from error
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise CodexAvailabilityError("Неизвестная версия Codex availability state")
        return {**self._default_state(), **payload}

    def _write_unlocked(self, state: Mapping[str, object]) -> None:
        fd, temp_name = tempfile.mkstemp(
            prefix=".codex-availability.",
            dir=str(self.root),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(dict(state), handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, self.path)
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass

    def _ensure_state(self) -> None:
        with self._lock(exclusive=True):
            if not self.path.exists():
                self._write_unlocked(self._default_state())

    @staticmethod
    def _effective(state: dict[str, Any]) -> dict[str, Any]:
        result = dict(state)
        if bool(result.get("manual_hold")):
            result["codex_available"] = False
            result["reason"] = "manual_hold"
        elif result.get("provider_available") is True:
            result["codex_available"] = True
            result["reason"] = "available"
        elif result.get("provider_available") is False:
            result["codex_available"] = False
            result["reason"] = str(
                result.get("provider_reason") or "subscription_unavailable"
            )
        else:
            result["codex_available"] = False
            result["reason"] = "unknown"
        return result

    def status(self) -> dict[str, Any]:
        with self._lock(exclusive=False):
            return self._effective(self._load_unlocked())

    @property
    def codex_available(self) -> bool:
        return self.status().get("codex_available") is True

    @property
    def codex_available_at(self) -> int | None:
        return _epoch(self.status().get("codex_available_at"))

    def _update(self, mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        with self._lock(exclusive=True):
            state = self._load_unlocked()
            mutator(state)
            state = self._effective(state)
            self._write_unlocked(state)
            result = dict(state)
        self._wake.set()
        return result

    def refresh(
        self,
        *,
        source: str,
        periodic: bool = False,
    ) -> dict[str, Any]:
        now = int(self.clock())
        try:
            snapshot = self.probe()
            available, available_at = classify_rate_limits(snapshot, now_epoch=now)
        except Exception as error:
            def failed(state: dict[str, Any]) -> None:
                state["last_checked_at"] = now
                state["last_check_source"] = source
                state["last_error"] = str(error)[:1000] or type(error).__name__
                if periodic:
                    state["last_periodic_check_at"] = now
                    state["next_periodic_check_at"] = now + self.refresh_seconds
                # Unknown startup remains false. A transient probe error does not
                # invent a different value over an already-known provider state.
            return self._update(failed)

        def observed(state: dict[str, Any]) -> None:
            state["provider_available"] = available
            state["provider_reason"] = (
                "available" if available else "subscription_limit"
            )
            state["codex_available_at"] = available_at
            state["rate_limits"] = snapshot
            state["last_checked_at"] = now
            state["last_check_source"] = source
            state["last_error"] = None
            if periodic:
                state["last_periodic_check_at"] = now
                state["next_periodic_check_at"] = now + self.refresh_seconds
            # Expired manual holds disappear only after a successful live probe.
            # Time passing alone never turns Codex back on.
            if bool(state.get("manual_hold")):
                hold_until = _epoch(state.get("manual_hold_until"))
                if hold_until is not None and hold_until <= now:
                    state["manual_hold"] = False
                    state["manual_hold_until"] = None
        return self._update(observed)

    def note_subscription_failure(
        self,
        reason: str = "subscription_limit",
    ) -> dict[str, Any]:
        now = int(self.clock())

        def blocked(state: dict[str, Any]) -> None:
            state["provider_available"] = False
            state["provider_reason"] = reason or "subscription_unavailable"
            state["last_checked_at"] = now
            state["last_check_source"] = "execution_failure"
            state["last_error"] = None
        self._update(blocked)
        # Best effort live read obtains the provider's real resets_at. The flag
        # is already false before this potentially failing diagnostic call.
        return self.refresh(source="execution_failure_refresh")

    def hold(self, until: str) -> dict[str, Any]:
        raw = until.strip()
        if raw.casefold() == "auto":
            refreshed = self.refresh(source="manual_hold_auto_probe")
            if refreshed.get("provider_available") is not False:
                raise CodexAvailabilityError(
                    "Codex не сообщает активный subscription limit; для ручного hold укажите явный --until"
                )
            hold_until = _epoch(refreshed.get("codex_available_at"))
            if hold_until is None:
                raise CodexAvailabilityError(
                    "Codex не сообщил resets_at; укажите явный --until"
                )
        else:
            hold_until = parse_until(raw, now_epoch=self.clock())

        def apply(state: dict[str, Any]) -> None:
            state["manual_hold"] = True
            state["manual_hold_until"] = hold_until
        return self._update(apply)

    def clear(self) -> dict[str, Any]:
        def remove(state: dict[str, Any]) -> None:
            state["manual_hold"] = False
            state["manual_hold_until"] = None
            # Until the immediate live refresh succeeds, do not resurrect Codex
            # merely from a stale pre-hold true value.
            state["provider_available"] = None
            state["provider_reason"] = "unknown"
        self._update(remove)
        return self.refresh(source="manual_clear")

    def _next_due(self, state: Mapping[str, object], now: float) -> float:
        candidates: list[float] = []
        last_checked = _epoch(state.get("last_checked_at")) or 0
        periodic = _epoch(state.get("next_periodic_check_at"))
        if periodic is not None:
            candidates.append(float(periodic))
        else:
            candidates.append(now)
        if state.get("provider_available") is False:
            recovery = _epoch(state.get("codex_available_at"))
            if recovery is not None and last_checked < recovery:
                candidates.append(float(recovery))
        if bool(state.get("manual_hold")):
            hold_until = _epoch(state.get("manual_hold_until"))
            if hold_until is not None and last_checked < hold_until:
                candidates.append(float(hold_until))
        return min(candidates) if candidates else now + self.refresh_seconds

    def _background_loop(self) -> None:
        # Startup probe establishes the first real dynamic value and starts the
        # independent five-hour cadence.
        self.refresh(source="startup", periodic=True)
        while True:
            self._wake.clear()
            state = self.status()
            now = self.clock()
            due = self._next_due(state, now)
            if due > now:
                # The one-minute wake is a local state-file poll only. It does
                # not call OpenAI. This lets an external operator CLI move a
                # manual hold/clear deadline without waiting for the old sleep.
                timeout = min(max(1.0, due - now), float(STATE_POLL_SECONDS))
                self._wake.wait(timeout=timeout)
                if self._wake.is_set():
                    continue
                # Re-read persisted state because another process may have
                # changed it. If the real due time is still in the future, the
                # loop sleeps again without performing a provider request.
                state = self.status()
                now = self.clock()
                if self._next_due(state, now) > now:
                    continue

            last_checked = _epoch(state.get("last_checked_at")) or 0
            hold_until = _epoch(state.get("manual_hold_until"))
            if (
                bool(state.get("manual_hold"))
                and hold_until is not None
                and hold_until <= now
                and last_checked < hold_until
            ):
                self.refresh(source="manual_hold_expiry")
                continue

            recovery = _epoch(state.get("codex_available_at"))
            if (
                state.get("provider_available") is False
                and recovery is not None
                and recovery <= now
                and last_checked < recovery
            ):
                self.refresh(source="provider_reset_at")
                continue

            periodic = _epoch(state.get("next_periodic_check_at"))
            if periodic is None or periodic <= now:
                self.refresh(source="periodic_5h", periodic=True)
                continue

    def start_background(self) -> None:
        with self._background_lock:
            if self._background_started:
                return
            self._background_started = True
            threading.Thread(
                target=self._background_loop,
                name="codex-availability-watch",
                daemon=True,
            ).start()


__all__ = (
    "CodexAvailabilityError",
    "CodexAvailabilityGate",
    "DEFAULT_REFRESH_SECONDS",
    "STATE_POLL_SECONDS",
    "classify_rate_limits",
    "parse_until",
)
