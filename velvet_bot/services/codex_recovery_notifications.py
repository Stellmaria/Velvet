from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping

from aiogram import Bot

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://hermes-coder-router:8878"
_DEFAULT_STATE_PATH = Path("/app/runtime/codex-recovery-notifications.json")
_DEFAULT_PROJECTS = ("velvet", "max")
_SUBSCRIPTION_REASONS = frozenset({"subscription_limit", "subscription_unavailable"})
_FETCH_TIMEOUT_SECONDS = 8


class CodexRecoveryStateError(RuntimeError):
    pass


def _positive_epoch(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(float(value))
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


@dataclass(frozen=True, slots=True)
class CodexAvailabilitySnapshot:
    project: str
    codex_available: bool
    provider_available: bool | None
    reason: str
    provider_reason: str
    last_checked_at: int | None
    last_check_source: str | None
    last_error: str | None
    codex_available_at: int | None
    next_periodic_check_at: int | None
    plan_type: str | None

    @property
    def subscription_limited(self) -> bool:
        return (
            self.provider_available is False
            and self.provider_reason in _SUBSCRIPTION_REASONS
            and not self.codex_available
        )

    @property
    def confirmed_recovered(self) -> bool:
        return (
            self.provider_available is True
            and self.codex_available
            and self.provider_reason == "available"
            and self.reason == "available"
            and self.last_error is None
            and self.last_checked_at is not None
            and bool(self.last_check_source)
        )


def _parse_availability(project: str, payload: Mapping[str, object]) -> CodexAvailabilitySnapshot:
    routing = payload.get("routing")
    if not isinstance(routing, Mapping):
        raise CodexRecoveryStateError(f"Coder {project} не вернул routing state")
    state = routing.get("codex_availability")
    if not isinstance(state, Mapping):
        raise CodexRecoveryStateError(f"Coder {project} не вернул codex availability state")
    provider_available_raw = state.get("provider_available")
    provider_available = (
        provider_available_raw if isinstance(provider_available_raw, bool) else None
    )
    rate_limits = state.get("rate_limits")
    plan_type: str | None = None
    if isinstance(rate_limits, Mapping):
        raw_plan = str(rate_limits.get("plan_type") or "").strip().casefold()
        plan_type = raw_plan or None
    last_error_raw = state.get("last_error")
    last_error = str(last_error_raw).strip() if last_error_raw else None
    source_raw = state.get("last_check_source")
    source = str(source_raw).strip() if source_raw else None
    return CodexAvailabilitySnapshot(
        project=project,
        codex_available=state.get("codex_available") is True,
        provider_available=provider_available,
        reason=str(state.get("reason") or "unknown").strip().casefold(),
        provider_reason=str(state.get("provider_reason") or "unknown").strip().casefold(),
        last_checked_at=_positive_epoch(state.get("last_checked_at")),
        last_check_source=source,
        last_error=last_error,
        codex_available_at=_positive_epoch(state.get("codex_available_at")),
        next_periodic_check_at=_positive_epoch(state.get("next_periodic_check_at")),
        plan_type=plan_type,
    )


def _read_capabilities_json(
    *,
    project: str,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
) -> Mapping[str, object]:
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/coders/{project}/capabilities",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "VelvetBot/1.0 codex-recovery-monitor",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise CodexRecoveryStateError(
            f"Coder router вернул HTTP {error.code} для {project}"
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise CodexRecoveryStateError(f"Coder router недоступен для {project}") from error
    except json.JSONDecodeError as error:
        raise CodexRecoveryStateError(
            f"Coder router вернул повреждённый JSON для {project}"
        ) from error
    if not isinstance(payload, Mapping):
        raise CodexRecoveryStateError(f"Coder router вернул неизвестный формат для {project}")
    return payload


async def fetch_codex_availability_snapshot(
    *,
    project: str,
    base_url: str,
    api_key: str,
    timeout_seconds: int = _FETCH_TIMEOUT_SECONDS,
) -> CodexAvailabilitySnapshot:
    payload = await asyncio.to_thread(
        _read_capabilities_json,
        project=project,
        base_url=base_url,
        api_key=api_key,
        timeout_seconds=timeout_seconds,
    )
    return _parse_availability(project, payload)


SnapshotFetcher = Callable[[str], Awaitable[CodexAvailabilitySnapshot]]


class CodexRecoveryNotificationStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    @staticmethod
    def _default_state() -> dict[str, Any]:
        return {
            "version": 1,
            "active_limit_event_id": None,
            "active_limit_observed_at": None,
            "active_limit_checked_at": None,
            "last_notified_event_id": None,
            "last_notified_at": None,
        }

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._default_state()
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CodexRecoveryStateError(
                f"Повреждён Codex recovery notification state: {type(error).__name__}"
            ) from error
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise CodexRecoveryStateError("Неизвестная версия Codex recovery notification state")
        return {**self._default_state(), **payload}

    def save(self, state: Mapping[str, object]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            dir=str(self.path.parent),
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


def _format_epoch(value: int | None) -> str | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value, UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def _plan_label(value: str | None) -> str | None:
    if not value:
        return None
    return {
        "plus": "Plus",
        "pro": "Pro",
        "team": "Team",
        "business": "Business",
        "enterprise": "Enterprise",
    }.get(value, value)


def _render_recovery_message(snapshots: tuple[CodexAvailabilitySnapshot, ...]) -> str:
    recovered_at = max(
        (item.last_checked_at for item in snapshots if item.last_checked_at is not None),
        default=None,
    )
    next_periodic = min(
        (
            item.next_periodic_check_at
            for item in snapshots
            if item.next_periodic_check_at is not None
        ),
        default=None,
    )
    plan = next((item.plan_type for item in snapshots if item.plan_type), None)
    lines = [
        "Codex снова доступен.",
        "Лимит подписки восстановлен, primary Codex routing включсн.",
    ]
    details: list[str] = []
    recovered_label = _format_epoch(recovered_at)
    if recovered_label:
        details.append(f"Восстановление: {recovered_label}")
    periodic_label = _format_epoch(next_periodic)
    if periodic_label:
        details.append(f"Следующая плановая проверка: {periodic_label}")
    plan_label = _plan_label(plan)
    if plan_label:
        details.append(f"План: {plan_label}")
    if details:
        lines.extend(["", *details])
    return "\n".join(lines)


class CodexRecoveryNotificationMonitor:
    def __init__(
        self,
        *,
        bot: Bot,
        owner_chat_id: int,
        fetch_snapshot: SnapshotFetcher,
        state_path: Path = _DEFAULT_STATE_PATH,
        projects: tuple[str, ...] = _DEFAULT_PROJECTS,
    ) -> None:
        if not projects:
            raise ValueError("Codex recovery monitor требует хотя бы один project")
        self._bot = bot
        self._owner_chat_id = int(owner_chat_id)
        self._fetch_snapshot = fetch_snapshot
        self._projects = tuple(dict.fromkeys(projects))
        self._store = CodexRecoveryNotificationStore(state_path)
        self._lock = asyncio.Lock()

    async def _read_all(self) -> tuple[CodexAvailabilitySnapshot, ...] | None:
        results = await asyncio.gather(
            *(self._fetch_snapshot(project) for project in self._projects),
            return_exceptions=True,
        )
        if any(isinstance(result, BaseException) for result in results):
            for project, result in zip(self._projects, results, strict=True):
                if isinstance(result, BaseException):
                    logger.info(
                        "Codex recovery state read failed project=%s error=%s",
                        project,
                        type(result).__name__,
                    )
            return None
        return tuple(
            result
            for result in results
            if isinstance(result, CodexAvailabilitySnapshot)
        )

    async def process_once(self) -> int:
        async with self._lock:
            snapshots = await self._read_all()
            if snapshots is None or len(snapshots) != len(self._projects):
                return 0
            state = self._store.load()
            limited = tuple(item for item in snapshots if item.subscription_limited)
            if limited:
                if not state.get("active_limit_event_id"):
                    state["active_limit_event_id"] = uuid.uuid4().hex
                    state["active_limit_observed_at"] = int(datetime.now(UTC).timestamp())
                checked = max(
                    (item.last_checked_at for item in limited if item.last_checked_at is not None),
                    default=None,
                )
                if checked is not None:
                    previous = _positive_epoch(state.get("active_limit_checked_at")) or 0
                    state["active_limit_checked_at"] = max(previous, checked)
                self._store.save(state)
                return 0

            active_event = str(state.get("active_limit_event_id") or "").strip()
            if not active_event:
                return 0
            if state.get("last_notified_event_id") == active_event:
                state["active_limit_event_id"] = None
                state["active_limit_observed_at"] = None
                state["active_limit_checked_at"] = None
                self._store.save(state)
                return 0
            if not all(item.confirmed_recovered for item in snapshots):
                return 0
            limited_checked_at = _positive_epoch(state.get("active_limit_checked_at"))
            if limited_checked_at is not None and any(
                item.last_checked_at is None or item.last_checked_at <= limited_checked_at
                for item in snapshots
            ):
                return 0

            # Claim the recovery event durably before the non-transactional
            # Telegram call. Bot API sendMessage has no application-level
            # idempotency key, so this ordering deliberately prefers at-most-once
            # delivery over a duplicate after a process crash or ambiguous network
            # failure.
            state["last_notified_event_id"] = active_event
            state["last_notified_at"] = int(datetime.now(UTC).timestamp())
            state["active_limit_event_id"] = None
            state["active_limit_observed_at"] = None
            state["active_limit_checked_at"] = None
            self._store.save(state)
            await self._bot.send_message(
                chat_id=self._owner_chat_id,
                text=_render_recovery_message(snapshots),
                disable_web_page_preview=True,
            )
            return 1


def build_codex_recovery_notification_monitor(
    *,
    bot: Bot,
    owner_chat_id: int | None,
) -> CodexRecoveryNotificationMonitor | None:
    if owner_chat_id is None:
        return None
    api_key = os.getenv("CODEX_LIMITS_API_KEY", "").strip()
    base_url = os.getenv("CODEX_LIMITS_BASE_URL", _DEFAULT_BASE_URL).strip().rstrip("/")
    if not api_key or not base_url:
        return None

    async def fetch(project: str) -> CodexAvailabilitySnapshot:
        return await fetch_codex_availability_snapshot(
            project=project,
            base_url=base_url,
            api_key=api_key,
        )

    return CodexRecoveryNotificationMonitor(
        bot=bot,
        owner_chat_id=owner_chat_id,
        fetch_snapshot=fetch,
    )


__all__ = (
    "CodexAvailabilitySnapshot",
    "CodexRecoveryNotificationMonitor",
    "CodexRecoveryNotificationStore",
    "CodexRecoveryStateError",
    "build_codex_recovery_notification_monitor",
    "fetch_codex_availability_snapshot",
)
